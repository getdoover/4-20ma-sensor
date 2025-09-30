import asyncio, time, logging

from pydoover.utils import apply_async_kalman_filter

class Sensor420ma:
    def __init__(self, pin_no, plt_iface, calibration, process_variance=0.5):
        self.max_values = 10
        self.pin_no = pin_no
        self.process_variance = process_variance
        # self.data_store = {}
        self.plt_iface = plt_iface
        self.data_store = []
        self.reading = [0,0,0,0]
        self.calibration_low = calibration[0]
        self.calibration_high = calibration[1] 
        self.calibration_range = self.calibration_high - self.calibration_low
        self.raw_value = None
        self.filtered_val = 0
        self.reading_count = 0

    ## ensure there is 2 entries for each data series
    def is_initialised(self):
        initialised = True
        res = [x for x in self.data_store if x is not None][-3:]
        
        if len(res) < 3:
            initialised = False
        return initialised
    
    def get_pin_no(self):
        return self.pin_no
    
    ## give a key and value and it will be added to the data store
    def add_record(self, value):
        if value is not None:
            self.data_store.append(value)
            while len(self.data_store) > self.max_values:
                self.data_store.pop(0)
            return True
        return False

    def get_last(self):
        if len(self.data_store) < 1:
            return None
        return self.data_store[-1]
    
    def get_avg(self):
        if self.is_initialised():
            total = sum([x for x in self.data_store if x is not None][-3:])
            avg = total/3
            return avg
        else:
            return None
        
    @apply_async_kalman_filter()
    async def get_reading(self, kf_process_variance=None, _reading = None):
        if _reading is None:
            reading = await self.plt_iface.get_ai(self.pin_no)
        else:
            reading = _reading
            
        if reading is None:
            return None
        self.raw_value = reading
        if reading < 3.5:
            print("reading is less than 3.5, skipping...")
            self.reading_count += 1
            return None
        return reading

    async def update(self, _reading = None):
        reading = await self.get_reading(
            kf_process_variance=self.process_variance, 
            _reading=_reading
        )
        value = self.convert_reading(reading)
        self.filtered_val = value

        self.add_record( value )

    def convert_reading(self, reading):
        if reading is None:
            return None
        reading = reading - 4
        if reading < 0 and reading > -0.5:
            reading = 0
        converted = (reading/16)*self.calibration_range + self.calibration_low
        return converted
        
    async def get_raw_reading(self):
        val =  await self.plt_iface.get_ai(self.pin_no)
        return self.convert_reading(val)
    
    @property
    def value(self):
        if self.is_initialised():
            return self.filtered_val
        else:
            return None