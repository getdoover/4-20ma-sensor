from pydoover import ui
from .app_config import Sensor420maConfig

class Sensor420maUI:
    def __init__(self, config: Sensor420maConfig):
        self.config = config
        self.filtered_value = ui.NumericVariable(
            "ai_value",
            f"{self.config.input_name.value}{self.config.disp_string_units})"
            )
        
    def fetch(self):
        return self.filtered_value

    def update(self, filtered_value):
        self.filtered_value.update(filtered_value)

