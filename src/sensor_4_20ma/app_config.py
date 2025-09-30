from pathlib import Path

from pydoover import config


class Sensor420maConfig(config.Schema):
    def __init__(self):
        # AI Pin Configuration
        self.ai_pin = config.Integer(
            "AI Pin Number", 
            default=0,
            description="The analog input pin number for the 4-20mA sensor",
            minimum=0,
            maximum=15
        )
        
        self.input_name = config.String(
            "Name for the Input that appears in the UI",
        )
        
        # 4-20mA Signal Range Configuration
        self.signal_low_range = config.Number(
            "Signal Low Range (4mA)",
            default=0.0,
            description="The physical value corresponding to 4mA signal (minimum sensor reading)"
        )
        
        self.signal_high_range = config.Number(
            "Signal High Range (20mA)", 
            default=100.0,
            description="The physical value corresponding to 20mA signal (maximum sensor reading)"
        )
        
        # Units Configuration
        self.measurement_units = config.String(
            "Measurement Units",
            default="%",
            description="The units for the sensor measurement (e.g., %, °C, PSI, etc.)"
        )
        
        # Signal Processing Configuration
        self.signal_filter_enabled = config.Boolean(
            "Enable Signal Filtering",
            default=True,
            description="Enable digital filtering to smooth out sensor readings"
        )
        
        self.process_variance = config.Number(
            "Process Variance",
            default=0.5,
            description="The process variance for the Kalman Filter running on the in put"
        )
        
        ## Alarms
        alarm = config.Object("Alarm", description="Alarm configuration")
        alarm.add_elements(
            config.Number("Alarm Threshold", default=0.0, description="The threshold for the alarm", minimum=0.0, maximum=100.0),
            config.String("Alarm Message", default="Alarm", description="The message for the alarm"),
            config.Boolean("Alarm Enabled", default=False, description="Enable the alarm"),
            config.Boolean("Alarm Active", default=False, description="Enable the alarm"),
            config.Boolean("Alarm Reset", default=False, description="Reset the alarm"),
        )

def export():
    Sensor420maConfig().export(Path(__file__).parents[2] / "doover_config.json", "4_20ma_sensor")

if __name__ == "__main__":
    export()
