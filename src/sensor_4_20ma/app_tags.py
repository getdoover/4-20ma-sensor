from pydoover.tags import Tag, Tags


class Sensor420maTags(Tags):
    value = Tag("number", default=None, live=True)
    unfiltered_value = Tag("number", default=None)
    raw_value = Tag("number", default=None)
    polling_frequency = Tag("number", default=None)
    # Operator sensor calibration readbacks (operator_calibration.py): the
    # values in effect, published only while the feature is enabled.
    range_low = Tag("number", default=None, live=True)
    range_high = Tag("number", default=None, live=True)
    offset = Tag("number", default=None, live=True)
    operator_calibration = Tag("boolean", default=None, live=True)
    # Alarm gate (alarm.alarm_enable_tag): published only while it is set.
    alarm_armed = Tag("boolean", default=None, live=True)
    alarm_status = Tag("string", default=None, live=True)
    # Sensor fault alarm: published only while it is enabled.
    sensor_fault = Tag("boolean", default=None, live=True)
    sensor_status = Tag("string", default=None, live=True)
