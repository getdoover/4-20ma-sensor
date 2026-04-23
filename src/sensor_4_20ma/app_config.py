from pathlib import Path

from pydoover import config


class AlarmConfig(config.Object):
    alarm_threshold = config.Number(
        "Alarm Threshold", default=0.0, description="The threshold for the alarm", minimum=0.0, maximum=100.0,
    )
    alarm_message = config.String(
        "Alarm Message", default="Alarm", description="The message for the alarm",
    )
    alarm_enabled = config.Boolean(
        "Alarm Enabled", default=False, description="Enable the alarm",
    )
    alarm_active = config.Boolean(
        "Alarm Active", default=False, description="Enable the alarm",
    )
    alarm_reset = config.Boolean(
        "Alarm Reset", default=False, description="Reset the alarm",
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


def export():
    Sensor420maConfig.export(Path(__file__).parents[2] / "doover_config.json", "4_20ma_sensor")
