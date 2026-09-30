import logging
import time

from pydoover import ui
from pydoover.docker import Application

from .alarm import Alarm, AlarmType, evaluate
from .app_config import Sensor420maConfig
from .app_notifications import Sensor420maNotifications
from .app_tags import Sensor420maTags
from .app_ui import Sensor420maUI
from .operator_calibration import RESET, RPC_PATTERN, OperatorCalibration
from .sensor import Sensor420ma

log = logging.getLogger()

# Bounded wait for the ui_cmds aggregate at startup (operator calibration only).
UI_CMDS_SYNC_TIMEOUT_SECS = 10
UI_CMDS_SYNC_POLL_SECS = 0.25


class Sensor420maApplication(Application):
    config_cls = Sensor420maConfig
    tags_cls = Sensor420maTags
    ui_cls = Sensor420maUI
    notifications_cls = Sensor420maNotifications

    async def setup(self):
        self.started = time.time()

        self.default_polling_frequency = min(self.config.sample_rate.value, 5.0)
        self._set_polling_frequency(self.default_polling_frequency)

        await self.tags.polling_frequency.set(self.default_polling_frequency)

        self.subscribe_to_tag("polling_frequency", self._on_polling_frequency_changed)

        self.sensor = Sensor420ma(
            int(self.config.ai_pin.value),
            self.platform_iface,
            [self.config.min_range.value, self.config.max_range.value],
            self.config.process_variance.value,
            measurement_variance=self.config.measurement_variance.value,
            filter_enabled=self.config.signal_filter_enabled.value,
        )

        self.alarm = Alarm(
            grace_period=self.config.alarm.grace_period.value,
            renotify_interval=self.config.alarm.renotify_interval.value,
        )

        # The flag is held from here on (see OperatorCalibration.latch_enabled).
        if self.calibration.latch_enabled():
            # The operator values live in ui_cmds, which pydoover subscribes
            # but does not wait for; an offline boot falls back to the tags.
            self.ui_cmds_synced = await self._await_ui_cmds_sync()
            self.calibration.restore()
        else:
            await self.calibration.clear_stale_tags()

    @property
    def calibration(self) -> OperatorCalibration:
        """Operator sensor calibration. Created on first use: its RPCs can
        arrive before setup() has run."""
        calibration = self.__dict__.get("_calibration")
        if calibration is None:
            calibration = self._calibration = OperatorCalibration(self)
        return calibration

    async def _await_ui_cmds_sync(self) -> bool:
        """Wait (bounded) for ui_cmds and confirm it was delivered. Never
        raises; False on timeout or when the device agent cannot serve it
        (offline reboot).

        pydoover marks a channel synced even when seeding its aggregate
        failed, so the wait alone does not mean the values arrived. The
        aggregate is fetched as well (pydoover does the same for
        deployment_config): from the cache when the seed worked, else from
        the device agent, which raises when it cannot serve it. A fetched
        aggregate that ui_manager has not seen yet (a failed seed, or its
        sync event not dispatched yet) is handed to it, as its own sync
        event would.
        """
        try:
            synced = await self.device_agent.wait_for_channels_sync(
                ["ui_cmds"],
                timeout=UI_CMDS_SYNC_TIMEOUT_SECS,
                inter_wait=UI_CMDS_SYNC_POLL_SECS,
            )
            aggregate = None
            if synced:
                aggregate = await self.device_agent.fetch_channel_aggregate("ui_cmds")
        except Exception as e:  # noqa: BLE001 - must not stop the app starting
            log.warning(
                f"Could not read ui_cmds: {e}; using the persisted calibration "
                "tags until it syncs"
            )
            return False
        if not synced:
            log.warning(
                f"ui_cmds did not sync within {UI_CMDS_SYNC_TIMEOUT_SECS}s; "
                "using the persisted calibration tags until it does"
            )
            return False
        data = getattr(aggregate, "data", None)
        values = data.get(self.app_key) if isinstance(data, dict) else None
        if isinstance(values, dict) and values and not self.ui_manager.values:
            self.ui_manager.values = values
        return True

    def _set_polling_frequency(self, hz):
        hz = max(0.1, min(hz, 5.0))
        self.loop_target_period = 1.0 / hz
        log.info(f"Polling frequency set to {hz} Hz (period: {self.loop_target_period:.3f}s)")

    async def _on_polling_frequency_changed(self, key, value):
        if value is None:
            return
        self._set_polling_frequency(float(value))
        log.info(f"Polling frequency updated by external app to {value} Hz")

    async def main_loop(self):
        calibration = None
        if self.calibration.enabled:
            await self.calibration.repersist()
            calibration = self.calibration.effective()
            self.sensor.set_calibration(*calibration)

        await self.sensor.update()
        filtered_reading = self.sensor.value
        raw_reading = self.sensor.raw_value

        await self.tags.value.set(filtered_reading)
        await self.tags.raw_value.set(raw_reading)

        if self.config.signal_filter_enabled.value:
            await self.tags.unfiltered_value.set(self.sensor.unfiltered_val)

        if calibration is not None:
            await self.calibration.publish_tags(calibration)

        await self._check_alarm(filtered_reading)

    @ui.handler(RPC_PATTERN, auto_update=False)
    async def on_calibration_value(self, ctx, value):
        """``range_low`` / ``range_high`` / ``offset`` (cloud input and HMI).

        No ``parser=float``: pydoover reports a parser exception as
        INTERNAL_ERROR, so the value is parsed in the handler and a
        non-numeric one gets INVALID like an out-of-range one. The value is
        persisted by the handler, so a refused one leaves the stored value.
        """
        return await self.calibration.request(ctx.method, value)

    @ui.handler(RESET, auto_update=False)
    async def on_reset_calibration(self, ctx, value):
        return await self.calibration.request_reset()

    @staticmethod
    def _slider_value(slider):
        """A slider the operator has never moved has no stored value, and these
        sliders have no default, so reading one raises. Treat that as unset."""
        try:
            return slider.value
        except KeyError:
            return None

    def _alarm_bounds(self):
        """Read the alarm setpoint(s) from whichever slider the mode is using.

        Returns (point, low, high). Any of them may be None when the operator
        has not moved the slider yet, which evaluate() treats as "no bound".
        """
        if self.config.alarm_type is AlarmType.allowed_range:
            value = self._slider_value(self.ui.alarm_range)
            # the dual slider reports [low, high]
            if not isinstance(value, (list, tuple)) or len(value) != 2:
                return None, None, None
            low, high = sorted(value)
            return None, low, high

        return self._slider_value(self.ui.alarm_point), None, None

    async def _check_alarm(self, reading):
        if not self.config.alarm.alarm_enabled.value:
            self.alarm.clear()
            return

        point, low, high = self._alarm_bounds()
        breach = evaluate(
            reading, self.config.alarm_type, point=point, low=low, high=high
        )

        if self.alarm.update(breach):
            # No title: the server substitutes the agent's display name, which
            # is the device name and is what an operator expects to see.
            await self.notifications.alarm.send(
                self._alarm_message(reading, breach)
            )

    @staticmethod
    def _format_value(value):
        return f"{round(value, 2):g}"

    def _alarm_message(self, reading, breach):
        units = self.config.measurement_units.value
        suffix = f" {units}" if units else ""
        return (
            f"{self.app_display_name} has {breach.direction.value} "
            f"{self._format_value(breach.bound)}{suffix} with a value of "
            f"{self._format_value(reading)}{suffix}"
        )
