from pydoover import ui

from .app_tags import Sensor420maTags


class Sensor420maUI(ui.UI):
    curr_val = ui.NumericVariable(
        "AI Value",
        value=Sensor420maTags.value,
    )

    async def setup(self):
        display_name = f"{self.config.input_name.value}{self.config.disp_string_units}"
        self.curr_val.display_name = display_name

def export():
    pass
