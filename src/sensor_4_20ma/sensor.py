import logging

from pydoover.utils import apply_async_kalman_filter

log = logging.getLogger(__name__)


class Sensor420ma:
    def __init__(self, pin_no, plt_iface, calibration, process_variance=0.5, measurement_variance=0.5, filter_enabled=True):
        self.max_values = 10
        self.pin_no = pin_no
        self.process_variance = process_variance
        self.measurement_variance = measurement_variance
        self.filter_enabled = filter_enabled
        self.plt_iface = plt_iface
        self.data_store = []
        self.reading = [0, 0, 0, 0]
        self.calibration_low = calibration[0]
        self.calibration_high = calibration[1]
        self.calibration_range = self.calibration_high - self.calibration_low
        self.raw_value = None
        self.filtered_val = 0
        self.unfiltered_val = None
        self.reading_count = 0

    def is_initialised(self):
        """True once at least three real readings have been recorded."""
        res = [x for x in self.data_store if x is not None][-3:]
        return len(res) >= 3

    def add_record(self, value):
        """Append a reading to the rolling store, capped at max_values."""
        if value is not None:
            self.data_store.append(value)
            while len(self.data_store) > self.max_values:
                self.data_store.pop(0)
            return True
        return False

    async def _fetch_reading(self, _reading=None):
        if _reading is None:
            reading = await self.plt_iface.fetch_ai(self.pin_no)
        else:
            reading = _reading

        if reading is None:
            return None
        self.raw_value = reading
        if reading < 3.5:
            log.debug("Reading %s mA is below the 3.5 mA floor, skipping", reading)
            self.reading_count += 1
            return None
        return reading

    @apply_async_kalman_filter()
    async def get_reading(self, _reading=None, **kwargs):
        # **kwargs absorbs the kf_* kwargs that apply_async_kalman_filter leaks
        # into the wrapped call. Still required at pydoover 1.9.1: the async
        # wrapper awaits func(*args, **kwargs) before popping the kf_* keys.
        return await self._fetch_reading(_reading=_reading)

    async def update(self, _reading=None):
        if self.filter_enabled:
            reading = await self.get_reading(
                kf_process_variance=self.process_variance,
                kf_measurement_variance=self.measurement_variance,
                _reading=_reading,
            )
        else:
            reading = await self._fetch_reading(_reading=_reading)

        value = self.convert_reading(reading)
        self.filtered_val = value
        self.unfiltered_val = self.convert_reading(self.raw_value)

        self.add_record(value)

    def convert_reading(self, reading):
        if reading is None:
            return None
        reading = reading - 4
        if reading < 0 and reading > -0.5:
            reading = 0
        converted = (reading / 16) * self.calibration_range + self.calibration_low
        return converted

    @property
    def value(self):
        if self.is_initialised():
            return self.filtered_val
        return None
