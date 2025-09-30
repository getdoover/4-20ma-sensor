import logging
import time

from pydoover.docker import Application
from pydoover import ui

from .app_config import Sensor420maConfig
from .app_ui import Sensor420maUI
from .sensor import Sensor420ma
from .alarm import Alarm

log = logging.getLogger()

class Sensor420maApplication(Application):
    config: Sensor420maConfig  # not necessary, but helps your IDE provide autocomplete!

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.started: float = time.time()
        self.ui: Sensor420maUI = None

    async def setup(self):
        self.loop_target_period = 0.5
        
        self.sensor = Sensor420ma(
            self.config.ai_pin.value,
            self.platform_iface,
            [self.config.min_range.value, self.config.max_range.value],
            self.config.process_variance.value,
        )
        
        self.ui = Sensor420maUI(self.config)
        self.ui_manager.add_children(*self.ui.fetch())

    async def main_loop(self):
        await self.sensor.update()
        filtered_reading = self.sensor.value
        raw_reading = self.sensor.raw_value
                
        self.ui.update(
            filtered_reading
        )
        
        await self.set_tags_async({
            "value":filtered_reading,
            "raw_value":raw_reading
        })
