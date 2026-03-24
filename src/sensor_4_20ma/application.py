import logging
import time

from pydoover.docker import Application

from .app_config import Sensor420maConfig
from .app_tags import Sensor420maTags
from .app_ui import Sensor420maUI
from .sensor import Sensor420ma

log = logging.getLogger()


class Sensor420maApplication(Application):
    config_cls = Sensor420maConfig
    tags_cls = Sensor420maTags
    ui_cls = Sensor420maUI

    async def setup(self):
        self.started = time.time()

        sample_rate = min(self.config.sample_rate.value, 5.0)
        self.loop_target_period = 1.0 / sample_rate

        self.sensor = Sensor420ma(
            int(self.config.ai_pin.value),
            self.platform_iface,
            [self.config.min_range.value, self.config.max_range.value],
            self.config.process_variance.value,
            filter_enabled=self.config.signal_filter_enabled.value,
        )

    async def main_loop(self):
        await self.sensor.update()
        filtered_reading = self.sensor.value
        raw_reading = self.sensor.raw_value

        await self.tags.value.set(filtered_reading)
        await self.tags.raw_value.set(raw_reading)
