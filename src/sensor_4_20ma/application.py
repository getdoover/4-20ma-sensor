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

        self.default_polling_frequency = min(self.config.sample_rate.value, 5.0)
        self._set_polling_frequency(self.default_polling_frequency)

        await self.tags.polling_frequency.set(self.default_polling_frequency)

        self.subscribe_to_tag("polling_frequency", self._on_polling_frequency_changed)

        self.sensor = Sensor420ma(
            int(self.config.ai_pin.value),
            self.platform_iface,
            [self.config.min_range.value, self.config.max_range.value],
            self.config.process_variance.value,
            measurement_variance=self.config.measurement_variance.value,
            filter_enabled=self.config.signal_filter_enabled.value,
        )

    def _set_polling_frequency(self, hz):
        hz = max(0.1, min(hz, 5.0))
        self.loop_target_period = 1.0 / hz
        log.info(f"Polling frequency set to {hz} Hz (period: {self.loop_target_period:.3f}s)")

    async def _on_polling_frequency_changed(self, key, value):
        if value is None:
            return
        self._set_polling_frequency(float(value))
        log.info(f"Polling frequency updated by external app to {value} Hz")

    async def main_loop(self):
        await self.sensor.update()
        filtered_reading = self.sensor.value
        raw_reading = self.sensor.raw_value

        await self.tags.value.set(filtered_reading)
        await self.tags.raw_value.set(raw_reading)

        if self.config.signal_filter_enabled.value:
            await self.tags.unfiltered_value.set(self.sensor.unfiltered_val)
