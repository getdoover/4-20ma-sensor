from pathlib import Path

from pydoover import config

from .alarm import AlarmType


class AlarmConfig(config.Object):
    alarm_enabled = config.Boolean(
        "Alarm Enabled",
        default=False,
        description="Send a notification when the reading crosses the alarm point",
    )
    alarm_type = config.Enum(
        "Alarm Type",
        choices=AlarmType,
        default=AlarmType.greater_than,
        description=(
            "Greater Than and Less Than alarm on a single point. Allowed Range "
            "alarms when the reading falls outside a low/high band."
        ),
    )
    slider_min = config.Number(
        "Alarm Slider Minimum",
        default=None,
        description="Lower bound of the alarm point slider. Defaults to Min Range.",
    )
    slider_max = config.Number(
        "Alarm Slider Maximum",
        default=None,
        description="Upper bound of the alarm point slider. Defaults to Max Range.",
    )
    grace_period = config.Number(
        "Alarm Grace Period (s)",
        default=30.0,
        description="How long the reading must stay out of bounds before notifying",
        minimum=0.0,
    )
    renotify_interval = config.Number(
        "Alarm Re-notify Interval (s)",
        default=900.0,
        description="How often to re-notify while the alarm remains active",
        minimum=0.0,
    )


class Sensor420maConfig(config.Schema):
    ai_pin = config.Integer(
        "AI Pin Number",
        default=0,
        description="The analog input pin number for the 4-20mA sensor",
        minimum=0,
        maximum=15,
    )
    input_name = config.String(
        "Input Name",
        description="Name for the Input that appears in the UI e.g. Tank Vol (L)",
    )
    min_range = config.Number(
        "Min Range",
        default=0.0,
        description="The physical value corresponding to 4mA signal (minimum sensor reading)",
    )
    max_range = config.Number(
        "Max Range",
        default=100.0,
        description="The physical value corresponding to 20mA signal (maximum sensor reading)",
    )
    measurement_units = config.String(
        "Measurement Units",
        default=None,
        description="The units for the sensor measurement (e.g., %, °C, PSI, etc.)",
    )
    signal_filter_enabled = config.Boolean(
        "Enable Signal Filtering",
        default=True,
        description="Enable digital filtering to smooth out sensor readings",
    )
    process_variance = config.Number(
        "Process Variance",
        default=0.5,
        description="The process variance for the Kalman Filter running on the input",
    )
    measurement_variance = config.Number(
        "Measurement Variance",
        default=0.5,
        description="The measurement variance for the Kalman Filter running on the input",
    )
    sample_rate = config.Number(
        "Sample Rate (Hz)",
        default=2.0,
        description="The sample rate in Hz for the main loop",
        minimum=0.1,
        maximum=5.0,
    )
    alarm = AlarmConfig("Alarm", description="Alarm configuration")

    @property
    def disp_string_units(self):
        if self.measurement_units.value is None:
            return ""
        else:
            return f" ({self.measurement_units.value})"

    @property
    def alarm_type(self) -> AlarmType:
        # config.Enum stringifies its default but maps injected values back to
        # members, so .value is a member or a str depending on whether the
        # deployment config was injected. Normalise to a member either way.
        value = self.alarm.alarm_type.value
        return value if isinstance(value, AlarmType) else AlarmType(value)

    @property
    def alarm_slider_min(self) -> float:
        value = self.alarm.slider_min.value
        return self.min_range.value if value is None else value

    @property
    def alarm_slider_max(self) -> float:
        value = self.alarm.slider_max.value
        return self.max_range.value if value is None else value


def export():
    Sensor420maConfig.export(Path(__file__).parents[2] / "doover_config.json", "4_20ma_sensor")
