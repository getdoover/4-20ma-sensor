"""Operator sensor calibration (1 October 2026).

Operators tune the sensor on site, from the cloud "Sensor Calibration"
submodule or the local HMI (the same RPCs), without a redeploy:

| Name         | Meaning                                     | Default without an operator value |
|--------------|---------------------------------------------|-----------------------------------|
| ``range_low``  | engineering value at 4 mA                 | config ``min_range``              |
| ``range_high`` | engineering value at 20 mA                | config ``max_range``              |
| ``offset``     | added after scaling                       | 0                                 |

Units are the config ``measurement_units``. Each name is the UI element, the
RPC method, the ui_cmds key and the readback tag (the value in effect). The
``operator_calibration`` tag is true while the feature is enabled.

"Reset to configured values" (``reset_calibration``) clears the operator
values. So that the cloud inputs show what is in effect, it writes each config
default into ui_cmds, together with a ``<name>_default`` marker holding the
same number: a ui_cmds value equal to its marker is "no operator value", so a
later change to the config default (Min Range / Max Range) still takes effect,
and is written back so the input shows it, where a plain stored number would
have become an operator value. Setting a value clears its marker.

The whole feature sits behind the config flag ``operator_calibration_enabled``
(default off). Off, the submodule is hidden, the RPCs are refused with
UNAVAILABLE, the readback tags are not published and the app behaves exactly
as it did before the feature existed.

Validation (RPC; anything else is INVALID and changes nothing): a finite
number with ``|value| <= 1e6``, ``range_high > range_low`` and
``|offset| <= range_high - range_low``, judged on the values that would be in
effect after the change. Values are kept to 4 decimal places.

The value in effect is the operator value when a valid one is set, else the
config default, read on every loop, so a change applies to the next reading.
The mapping is applied after the Kalman filter, which runs on the loop current
in mA, so a range change never disturbs the filter state.

The operator value lives in the app's own ui_cmds, so it survives a restart
and the cloud input shows an HMI change. Every write is one ui_cmds aggregate
update, so a value and its marker (and a reset's three values) arrive together
in one echo. :class:`OperatorValue` copes with ui_cmds not being synced yet,
with the echoes of the app's own writes and with an offline reboot the same
way the SIA controller's alarm delays and the analog level sensor's
calibration do.
"""

from __future__ import annotations

import logging
import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass

from pydoover.rpc import RPCError

log = logging.getLogger(__name__)

MAX_ABS_VALUE = 1e6
DECIMALS = 4


def parse_number(value) -> float | None:
    """*value* as a finite number within ``|value| <= 1e6``, rounded to 4 dp,
    or None when it is not one."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or abs(number) > MAX_ABS_VALUE:
        return None
    return round(number, DECIMALS)


def _config_number(config, attr: str, fallback: float) -> float:
    """A config number as the app has always read it, or *fallback* when it is
    missing or not a finite number."""
    try:
        value = getattr(config, attr).value
    except (AttributeError, KeyError):
        return fallback
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if math.isfinite(number) else fallback


def config_range_low(config) -> float:
    return _config_number(config, "min_range", 0.0)


def config_range_high(config) -> float:
    return _config_number(config, "max_range", 100.0)


def config_offset(config) -> float:
    return 0.0


@dataclass(frozen=True)
class CalibrationValue:
    name: str
    """UI element, RPC method, ui_cmds key and readback tag."""
    label: str
    """Operator text for the UI, logs and errors."""
    default: Callable[[object], float]
    """The value without an operator value, from the deployment config."""

    @property
    def marker(self) -> str:
        """ui_cmds key marking the stored value as the config default."""
        return f"{self.name}_default"


RANGE_LOW = CalibrationValue("range_low", "Range Low (at 4 mA)", config_range_low)
RANGE_HIGH = CalibrationValue("range_high", "Range High (at 20 mA)", config_range_high)
OFFSET = CalibrationValue("offset", "Offset", config_offset)

VALUES: tuple[CalibrationValue, ...] = (RANGE_LOW, RANGE_HIGH, OFFSET)
RESET = "reset_calibration"
ENABLED_TAG = "operator_calibration"

# The one ui_cmds handler for the three value RPCs (application).
RPC_PATTERN = re.compile("(?:" + "|".join(re.escape(v.name) for v in VALUES) + r")\Z")


def _ui_values(app) -> dict:
    try:
        values = app.ui_manager.values
    except AttributeError:
        return {}
    return values if isinstance(values, dict) else {}


# (value, marker) as read from ui_cmds, each as parse_number gives it.
Observed = tuple[float | None, float | None]


class OperatorValue:
    """One operator value with a config default on the running app.

    Every write (RPC, reset, :meth:`maintenance_payload`) is staged here, which
    puts it in effect at once, and then written to ui_cmds by
    :class:`OperatorCalibration`. The value in effect is held here rather than
    read back from ``ui_manager.values``, which only changes when an aggregate
    event arrives.

    A ui_cmds value is adopted when it differs from the one last seen there:
    at start-up once ui_cmds has synced (before that, or with none set, the
    default applies), and when it is changed directly in the aggregate. An
    invalid ui_cmds value is ignored. A value equal to its ``_default`` marker
    means "no operator value" (see the module docstring).

    The app's own writes come back as aggregate events in the order they were
    written, so each write, as its (value, marker) pair, is kept until its
    echo arrives (``_pending``). An echo is adopted only when no newer write is
    still waiting, so two quick writes never put the older value back in
    effect. Anything else is a direct edit and is adopted. An echo not seen
    within ``ECHO_TIMEOUT_SECS`` is forgotten, so it cannot hide a later direct
    edit of the same value.

    If ui_cmds first delivers a value after a local write (it synced late,
    e.g. offline at boot), that value predates the write: the write stays in
    effect and is stored again by :meth:`OperatorCalibration.repersist`.

    Offline reboot: when ui_cmds has not synced at start-up the last value in
    effect, persisted in the readback tag, is used (:meth:`restore`) until
    ui_cmds delivers.
    """

    ECHO_TIMEOUT_SECS = 60.0

    def __init__(self, app, spec: CalibrationValue):
        self.app = app
        self.spec = spec
        # In effect (None = no operator value, the default applies) and the
        # ui_cmds (value, marker) last seen, so a direct change is picked up
        # once.
        self._value: float | None = None
        self._seen: Observed | None = None
        # This app's writes not yet echoed back, oldest first: (observed, when).
        self._pending: list[tuple[Observed, float]] = []
        self._unsynced_write = False
        self._repersist = False
        # Restored from the readback tag at an offline boot; dropped if
        # ui_cmds then delivers without a value for this one.
        self._provisional = False

    @property
    def name(self) -> str:
        return self.spec.name

    def default(self) -> float:
        return self.spec.default(self.app.config)

    def _synced(self) -> bool:
        return self.spec.name in _ui_values(self.app)

    def _observed(self) -> Observed | None:
        values = _ui_values(self.app)
        if self.spec.name not in values:
            return None
        return (
            parse_number(values.get(self.spec.name)),
            parse_number(values.get(self.spec.marker)),
        )

    @staticmethod
    def _operator_value(observed: Observed) -> float | None:
        value, marker = observed
        return None if value == marker else value

    def restore(self, persisted) -> None:
        """Start-up: if ui_cmds did not sync, carry the value in effect before
        the reboot over from its readback tag (only one other than the config
        default, which the tag holds when no operator value was set). A value
        an RPC set while setup waited for ui_cmds is newer and is kept."""
        if getattr(self.app, "ui_cmds_synced", False) or self._synced():
            return
        if self._value is not None or self._pending:
            return
        number = parse_number(persisted)
        if number is None or number == round(self.default(), DECIMALS):
            return
        self._value = number
        self._provisional = True
        log.warning(
            "ui_cmds not synced: using the last %s in effect, %s, from the %s "
            "tag until it does",
            self.spec.label,
            number,
            self.spec.name,
        )

    def setting(self) -> float | None:
        """The operator value in effect, or None when none is set."""
        observed = self._observed()
        if observed is None and self._provisional and _ui_values(self.app):
            # ui_cmds has synced and holds no value for this one: the
            # restored value was the default of an older config.
            self._provisional = False
            self._value = None
        if self._pending:
            expired = time.monotonic() - self.ECHO_TIMEOUT_SECS
            self._pending = [p for p in self._pending if p[1] >= expired]
        if observed != self._seen:
            self._seen = observed
            if observed is not None and observed[0] is not None:
                stored = self._operator_value(observed)
                echoed = next(
                    (i for i, (o, _t) in enumerate(self._pending) if o == observed),
                    None,
                )
                if echoed is not None:
                    # Our own write; a newer one still on its way wins.
                    del self._pending[: echoed + 1]
                    if not self._pending:
                        self._value = stored
                elif self._unsynced_write and stored != self._value:
                    self._repersist = True
                else:
                    self._value = stored
                self._unsynced_write = False
                self._provisional = False
        return self._value

    def effective(self) -> float:
        """The value in effect: the operator value, else the config default."""
        setting = self.setting()
        return setting if setting is not None else self.default()

    # -- writing -----------------------------------------------------------------

    def stage(self, number: float | None) -> dict:
        """Put *number* in effect at once (None: no operator value, the config
        default applies) and return the ui_cmds keys that store it.

        Synchronous, so a check and the change it was checked for cannot be
        split by another request.
        """
        # Take in the ui_cmds value first, so one not yet seen is not adopted
        # over this write on the next read.
        self.setting()
        if not self._synced():
            self._unsynced_write = True
        self._value = number
        self._provisional = False
        return self._payload()

    def _payload(self) -> dict:
        """The ui_cmds keys for the value in effect, expecting their echo
        unless the aggregate already holds them (or will, from the last
        write), which sends none. No operator value is stored as the config
        default with its marker; an operator value clears the marker."""
        if self._value is not None:
            observed: Observed = (self._value, None)
        else:
            number = round(self.default(), DECIMALS)
            observed = (number, number)
        last = self._pending[-1][0] if self._pending else self._seen
        if observed != last:
            self._pending.append((observed, time.monotonic()))
        return {self.spec.name: observed[0], self.spec.marker: observed[1]}

    def snapshot(self) -> tuple:
        """The state a write changes, for :meth:`rollback` if it fails."""
        return (
            self._value,
            self._seen,
            list(self._pending),
            self._unsynced_write,
            self._repersist,
            self._provisional,
        )

    def rollback(self, state: tuple) -> None:
        """Undo a :meth:`stage` whose ui_cmds write failed, so the value in
        effect is the one before it."""
        (
            self._value,
            self._seen,
            pending,
            self._unsynced_write,
            self._repersist,
            self._provisional,
        ) = state
        self._pending = list(pending)

    def maintenance_payload(self) -> dict | None:
        """ui_cmds keys to write again, if any:

        - a late ui_cmds sync delivered an older value over a local write;
        - ui_cmds shows a reset value that is no longer the config default
          (the config changed since), so the cloud input would be stale.
        """
        self.setting()
        if self._repersist:
            self._repersist = False
            log.info(
                "ui_cmds synced an older %s; keeping %s", self.spec.label, self._value
            )
            return self._payload()
        observed = self._seen
        if (
            self._value is None
            and not self._pending
            and observed is not None
            and observed[0] is not None
            and observed[0] == observed[1]
        ):
            default = round(self.default(), DECIMALS)
            if default != observed[0]:
                log.info(
                    "Configured %s is now %s (was %s at the reset); updating ui_cmds",
                    self.spec.label,
                    default,
                    observed[0],
                )
                return self._payload()
        return None


class OperatorCalibration:
    """The three operator values of one sensor and the rules between them."""

    def __init__(self, app):
        self.app = app
        self.values = {v.name: OperatorValue(app, v) for v in VALUES}
        self._fallback_warned = False
        self._offset_warned = False
        # The readback tags hold the offline-reboot state until restore()
        # has read them, so an RPC during the startup wait must not publish.
        self._restored = False
        # The flag as setup() read it (latch_enabled); None before setup.
        self._enabled: bool | None = None

    def _config_enabled(self) -> bool:
        try:
            return bool(self.app.config.operator_calibration_enabled.value)
        except (AttributeError, KeyError):
            return False

    def latch_enabled(self) -> bool:
        """setup(): fix the flag for the life of this run and return it.

        pydoover injects a changed deployment config into the running app
        without restarting it, but the cloud submodule's ``hidden`` is only
        set in UI setup and the sensor is built from the config in setup(),
        like every other setting of this app. Holding the flag from setup
        keeps the conversion, the RPCs, the readback tags and the UI in step:
        a change of the flag takes effect at the next app start.
        """
        self._enabled = self._config_enabled()
        return self._enabled

    @property
    def enabled(self) -> bool:
        """The flag as latched at setup (an RPC before setup reads the
        config, which is already injected then)."""
        if self._enabled is None:
            return self._config_enabled()
        return self._enabled

    @property
    def units(self) -> str:
        try:
            units = self.app.config.measurement_units.value
        except (AttributeError, KeyError):
            units = None
        return f" {units}" if units else ""

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise RPCError(
                "UNAVAILABLE",
                "operator sensor calibration is not enabled on this sensor "
                "(config 'Operator Sensor Calibration')",
            )

    def _candidate(self) -> dict[str, float]:
        return {name: value.effective() for name, value in self.values.items()}

    def effective(self) -> tuple[float, float, float]:
        """(range_low, range_high, offset) for the conversion.

        If the operator and config values mix into ``range_high <=
        range_low`` (e.g. the config range changed after an operator set one
        end), the configured range is used until an operator fixes it. Then,
        if the offset is outside +/- that range (a ui_cmds value the RPC
        check never saw: a direct aggregate edit, or a range that shrank
        under it), the configured offset is used the same way.
        """
        c = self._candidate()
        low, high, offset = c[RANGE_LOW.name], c[RANGE_HIGH.name], c[OFFSET.name]
        if not high > low:
            cfg_low = self.values[RANGE_LOW.name].default()
            cfg_high = self.values[RANGE_HIGH.name].default()
            if (low, high) != (cfg_low, cfg_high):
                if not self._fallback_warned:
                    self._fallback_warned = True
                    log.warning(
                        "Operator range %s..%s is not increasing; using the "
                        "configured range %s..%s",
                        low,
                        high,
                        cfg_low,
                        cfg_high,
                    )
                low, high = cfg_low, cfg_high
        else:
            self._fallback_warned = False
        # abs(): a reversed config range (an inverted sensor) still converts.
        span = abs(high - low)
        if abs(offset) > span:
            cfg_offset = self.values[OFFSET.name].default()
            if not self._offset_warned:
                self._offset_warned = True
                log.warning(
                    "Operator offset %s is outside +/-%s (the range %s..%s); "
                    "using the configured offset %s",
                    offset,
                    span,
                    low,
                    high,
                    cfg_offset,
                )
            offset = cfg_offset
        else:
            self._offset_warned = False
        return low, high, offset

    def check(self, name: str, value) -> float:
        """*value* for *name* as it would be stored, or RPCError INVALID."""
        spec = self.values[name].spec
        number = parse_number(value)
        if number is None:
            raise RPCError(
                "INVALID",
                f"{spec.label} must be a number within +/-{MAX_ABS_VALUE:g}, "
                f"got {value!r}",
            )
        c = self._candidate()
        c[name] = number
        low, high, offset = c[RANGE_LOW.name], c[RANGE_HIGH.name], c[OFFSET.name]
        if not high > low:
            raise RPCError(
                "INVALID",
                f"Range High ({high:g}{self.units}) must be above Range Low "
                f"({low:g}{self.units})",
            )
        if abs(offset) > high - low:
            raise RPCError(
                "INVALID",
                f"Offset ({offset:g}{self.units}) must be within +/-"
                f"{high - low:g}{self.units} (the range)",
            )
        return number

    async def request(self, name: str, value) -> dict:
        """Set one operator value (RPC / cloud input)."""
        self._require_enabled()
        number = self.check(name, value)
        setting = self.values[name]
        saved = {setting: setting.snapshot()}
        await self._commit(setting.stage(number), saved)
        if self._restored:
            await self.publish_tags()
        log.info("%s set to %s%s", setting.spec.label, number, self.units)
        return {name: setting.effective()}

    async def request_reset(self) -> dict:
        """Clear the operator values: back to the config defaults, which are
        stored in ui_cmds with their markers, so the cloud inputs show them
        and a later config change still takes effect."""
        self._require_enabled()
        saved = {setting: setting.snapshot() for setting in self.values.values()}
        payload = {}
        for setting in self.values.values():
            payload.update(setting.stage(None))
        await self._commit(payload, saved)
        if self._restored:
            await self.publish_tags()
        log.info("Sensor calibration reset to the configured values")
        return {name: v.effective() for name, v in self.values.items()}

    async def _commit(self, payload: dict, saved: dict) -> None:
        """Store an RPC's change. If ui_cmds cannot be written (e.g. the DDA
        is down) the change is undone and the RPC fails, so the conversion,
        the readback tags and what a restart comes back to all keep the value
        from before it, and the operator's error is true."""
        try:
            await self._write(payload)
        except Exception as e:
            for setting, state in saved.items():
                setting.rollback(state)
            log.warning("Could not store the sensor calibration: %s", e)
            raise RPCError(
                "UNAVAILABLE", "could not store the sensor calibration, try again"
            ) from e

    async def _write(self, payload: dict) -> None:
        """One ui_cmds aggregate write, so a value and its marker (and a
        reset's three values) arrive together in one echo."""
        await self.app.update_channel_aggregate("ui_cmds", {self.app.app_key: payload})

    def restore(self) -> None:
        """Offline reboot: keep the values in effect before the restart. Must
        run before anything publishes the readback tags."""
        self._restored = True
        for name, setting in self.values.items():
            setting.restore(self.app.tags[name].get())

    async def repersist(self) -> None:
        """Every loop while enabled: write ui_cmds again where needed (see
        :meth:`OperatorValue.maintenance_payload`), in one aggregate write."""
        payload = {}
        for setting in self.values.values():
            keys = setting.maintenance_payload()
            if keys:
                payload.update(keys)
        if not payload:
            return
        try:
            await self._write(payload)
        except Exception as e:  # noqa: BLE001 - a UI write must not stop the loop
            log.warning("Could not store the sensor calibration: %s", e)

    async def publish_tags(
        self, calibration: tuple[float, float, float] | None = None
    ) -> None:
        """Readback tags: the values in effect and the enabled flag."""
        low, high, offset = calibration or self.effective()
        await self.app.tags[RANGE_LOW.name].set(low)
        await self.app.tags[RANGE_HIGH.name].set(high)
        await self.app.tags[OFFSET.name].set(offset)
        await self.app.tags[ENABLED_TAG].set(True)

    async def clear_stale_tags(self) -> None:
        """Disabled: clear readbacks left by an earlier enabled deployment so
        the HMI does not offer settings the app refuses. A deployment that
        never enabled the feature has none and nothing is written."""
        if self.app.tags[ENABLED_TAG].get() is None:
            return
        for name in (v.name for v in VALUES):
            await self.app.tags[name].set(None)
        await self.app.tags[ENABLED_TAG].set(None)
