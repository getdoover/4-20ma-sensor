from pydoover import ui

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

    async def setup(self):
        display_name = f"{self.config.input_name.value}{self.config.disp_string_units}"
        self.curr_val.display_name = display_name

        self.multiplot.display_name = display_name
        self.multiplot.title = display_name
        self.multiplot.hidden = not self.config.multiplot_enabled.value
        self.multiplot.series[0].display_name = display_name
        self.multiplot.series[0].units = self.config.measurement_units.value

def export():
    pass
