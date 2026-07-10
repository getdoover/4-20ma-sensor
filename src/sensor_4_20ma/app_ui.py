from pathlib import Path

from pydoover import ui

from .alarm import AlarmType
from .app_tags import Sensor420maTags


class Sensor420maUI(ui.UI):
    curr_val = ui.NumericVariable(
        "AI Value",
        value=Sensor420maTags.value,
    )
    multiplot = ui.Multiplot(
        "Multiplot",
        name="multiplot",
        series=[
            ui.Series("Value", value=Sensor420maTags.value, name="value", active=True),
        ],
        hidden=True,
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

    async def setup(self):
        display_name = f"{self.config.input_name.value}{self.config.disp_string_units}"
        self.curr_val.display_name = display_name

        self.multiplot.display_name = display_name
        self.multiplot.title = display_name
        self.multiplot.hidden = not self.config.multiplot_enabled.value
        self.multiplot.series[0].display_name = display_name
        self.multiplot.series[0].units = self.config.measurement_units.value

        self._setup_alarm()

    def _setup_alarm(self):
        alarm_type = self.config.alarm_type
        enabled = self.config.alarm.alarm_enabled.value
        is_range = alarm_type is AlarmType.allowed_range

        for slider in (self.alarm_point, self.alarm_range):
            slider.min_val = self.config.alarm_slider_min
            slider.max_val = self.config.alarm_slider_max
            slider.units = self.config.measurement_units.value

        self.alarm_point.hidden = not enabled or is_range
        self.alarm_range.hidden = not enabled or not is_range

        if alarm_type is AlarmType.greater_than:
            self.alarm_point.display_name = "High Alarm Point"
        elif alarm_type is AlarmType.less_than:
            self.alarm_point.display_name = "Low Alarm Point"


def export():
    Sensor420maUI(None, None, None).export(Path(__file__).parents[2] / "doover_config.json", "4_20ma_sensor")
