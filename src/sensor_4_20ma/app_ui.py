import json
from pathlib import Path

from pydoover import ui

from .alarm import AlarmType
from .app_tags import Sensor420maTags
from .operator_calibration import MAX_ABS_VALUE, RESET, VALUES


class Sensor420maUI(ui.UI):
    curr_val = ui.NumericVariable(
        "$config.app().input_name",
        value=Sensor420maTags.value,
        units="$config.app().measurement_units"
    )
    # A single slider reports a number and a dual slider reports [low, high], so
    # each mode gets its own element. One element toggling dual_slider would
    # leave behind a stored value of the wrong shape on every mode change.
    alarm_point = ui.Slider(
        "Alarm Point",
        name="alarm_point",
        dual_slider=False,
        inverted=False,
        hidden=True,
    )
    alarm_range = ui.Slider(
        "Allowed Range",
        name="alarm_range",
        dual_slider=True,
        inverted=False,
        hidden=True,
    )
    # Shown only when the alarm has an Alarm Enable Tag: armed, arming, or
    # why it is disarmed.
    alarm_status = ui.TextVariable(
        "Alarm Status",
        value=Sensor420maTags.alarm_status,
        name="alarm_status",
        hidden=True,
    )
    # Shown only when the Sensor Fault Alarm is enabled.
    sensor_status = ui.TextVariable(
        "Sensor Status",
        value=Sensor420maTags.sensor_status,
        name="sensor_status",
        hidden=True,
    )
    # Operator sensor calibration (operator_calibration.py). Hidden unless the
    # config enables it; the RPC handler validates, and the defaults follow the
    # config in setup.
    sensor_calibration = ui.Submodule(
        "Sensor Calibration",
        children=[
            *(
                ui.FloatInput(
                    value.label,
                    min_val=-MAX_ABS_VALUE,
                    max_val=MAX_ABS_VALUE,
                    default=value.default(None),
                    name=value.name,
                )
                for value in VALUES
            ),
            ui.Button(
                "Reset to configured values",
                requires_confirm=True,
                name=RESET,
            ),
        ],
        name="sensor_calibration",
        hidden=True,
    )

    async def setup(self):
        alarm_type = self.config.alarm_type
        enabled = self.config.alarm.alarm_enabled.value
        is_range = alarm_type is AlarmType.allowed_range

        for slider in (self.alarm_point, self.alarm_range):
            slider.min_val = self.config.alarm_slider_min
            slider.max_val = self.config.alarm_slider_max
            slider.units = self.config.measurement_units.value

        self.alarm_point.hidden = not enabled or is_range
        self.alarm_range.hidden = not enabled or not is_range

        # An inverted slider shades [value, max] instead of [min, value]. Invert
        # for Less Than so the shaded band is the range that does not alarm, the
        # same way it already reads for Greater Than.
        self.alarm_point.inverted = alarm_type is AlarmType.less_than

        if alarm_type is AlarmType.greater_than:
            self.alarm_point.display_name = "High Alarm Point"
        elif alarm_type is AlarmType.less_than:
            self.alarm_point.display_name = "Low Alarm Point"

        self._seed_alarm_defaults()
        self.alarm_status.hidden = not enabled or self.config.alarm_enable_tag is None
        self.sensor_status.hidden = not self.config.sensor_fault_alarm_enabled.value

        self._setup_sensor_calibration()

    def _seed_alarm_defaults(self):
        """Show the configured default setpoints on sliders never moved.

        The app falls back to the same values (Application._alarm_bounds), so
        what the slider shows is what it alarms on until an operator moves it.
        """
        point = self.config.alarm_default_point
        if point is not None:
            self.alarm_point.default = point
            self.alarm_point._value_location = f"$cmds.app().alarm_point::{point}"

        value_range = self.config.alarm_default_range
        if value_range is not None:
            self.alarm_range.default = value_range
            self.alarm_range._value_location = (
                f"$cmds.app().alarm_range::{json.dumps(value_range)}"
            )

    def _setup_sensor_calibration(self):
        enabled = bool(self.config.operator_calibration_enabled.value)
        self.sensor_calibration.hidden = not enabled
        units = self.config.measurement_units.value
        for value in VALUES:
            element = getattr(self.sensor_calibration, value.name)
            default = value.default(self.config)
            element.default = default
            # The shown value falls back to the default baked into the lookup
            # at construction, so point it at the config default too.
            element._value_location = f"$cmds.app().{value.name}::{default}"
            if units:
                element.display_name = f"{value.label} ({units})"


def export():
    Sensor420maUI(None, None, None).export(Path(__file__).parents[2] / "doover_config.json", "4_20ma_sensor")
