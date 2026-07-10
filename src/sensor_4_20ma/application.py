import logging
import time

from pydoover.docker import Application
from pydoover.models import NotificationSeverity

from .alarm import Alarm, AlarmType, evaluate
from .app_config import Sensor420maConfig
from .app_tags import Sensor420maTags
from .app_ui import Sensor420maUI
from .sensor import Sensor420ma

log = logging.getLogger()


class Sensor420maApplication(Application):
    config_cls = Sensor420maConfig
    tags_cls = Sensor420maTags
    ui_cls = Sensor420maUI

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
        await self.sensor.update()
        filtered_reading = self.sensor.value
        raw_reading = self.sensor.raw_value

        await self.tags.value.set(filtered_reading)
        await self.tags.raw_value.set(raw_reading)

        if self.config.signal_filter_enabled.value:
            await self.tags.unfiltered_value.set(self.sensor.unfiltered_val)

        await self._check_alarm(filtered_reading)

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
            await self.send_notification(
                self._alarm_message(reading, breach),
                title=f"{self.app_display_name} alarm",
                severity=NotificationSeverity.Warn,
            )

    def _alarm_message(self, reading, breach):
        units = self.config.measurement_units.value
        suffix = f" {units}" if units else ""
        return (
            f"{self.app_display_name} has {breach.direction.value} "
            f"{breach.bound:g}{suffix} with a value of {reading:g}{suffix}"
        )
