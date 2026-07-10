"""Tests for the application's alarm wiring: bounds, messages, and notifications.

These borrow the real methods off Sensor420maApplication rather than building one,
which needs a device agent connection.
"""

import pytest

from sensor_4_20ma.alarm import Alarm
from sensor_4_20ma.app_config import Sensor420maConfig
from sensor_4_20ma.application import Sensor420maApplication


class StubSlider:
    """Mimics Interaction.value, which raises KeyError when never set."""

    def __init__(self, value=KeyError):
        self._value = value

    @property
    def value(self):
        if self._value is KeyError:
            raise KeyError("slider")
        return self._value


class StubUI:
    def __init__(self, point=KeyError, alarm_range=KeyError):
        self.alarm_point = StubSlider(point)
        self.alarm_range = StubSlider(alarm_range)


class StubApp:
    app_display_name = "4-20mA Sensor"

    _slider_value = staticmethod(Sensor420maApplication._slider_value)
    _format_value = staticmethod(Sensor420maApplication._format_value)
    _alarm_bounds = Sensor420maApplication._alarm_bounds
    _alarm_message = Sensor420maApplication._alarm_message
    _check_alarm = Sensor420maApplication._check_alarm

    def __init__(self, config, ui):
        self.config = config
        self.ui = ui
        self.alarm = Alarm(grace_period=0.0, renotify_interval=900.0)
        self.published = []

    @property
    def sent(self):
        return [data["message"] for _channel, data in self.published]

    async def create_message(self, channel_name, data):
        self.published.append((channel_name, data))


def make_config(**alarm_overrides):
    config = Sensor420maConfig()
    config._inject_deployment_config(
        {
            "ai_pin_number": 0,
            "input_name": "Tank Vol",
            "min_range": 0.0,
            "max_range": 5000.0,
            "measurement_units": "L",
            "enable_signal_filtering": True,
            "process_variance": 0.5,
            "measurement_variance": 0.5,
            "sample_rate_hz": 2.0,
            "enable_multiplot": False,
            "alarm": {"alarm_enabled": True, **alarm_overrides},
        }
    )
    return config


@pytest.mark.asyncio
async def test_untouched_slider_does_not_crash_the_loop():
    app = StubApp(make_config(), StubUI())
    await app._check_alarm(4000)
    assert app.sent == []


@pytest.mark.asyncio
async def test_greater_than_notification_message():
    app = StubApp(make_config(), StubUI(point=3000))
    await app._check_alarm(4200.0)
    assert app.sent == ["4-20mA Sensor has exceeded 3000 L with a value of 4200 L"]


@pytest.mark.asyncio
async def test_notification_payload_matches_the_data_plane_contract():
    """severity must be the serde variant name, not the int pydoover emits.

    An int fails to deserialise server-side, and the server then falls back to
    sending the whole JSON payload as the message body. Omitting the title makes
    the server substitute the agent's display name.
    """
    app = StubApp(make_config(), StubUI(point=3000))
    await app._check_alarm(4200.0)

    channel, payload = app.published[0]
    assert channel == "notifications"
    assert payload["severity"] == "Warn"
    assert "title" not in payload
    assert set(payload) == {"message", "severity"}


@pytest.mark.asyncio
async def test_readings_are_rounded_to_two_decimal_places():
    app = StubApp(make_config(alarm_type="Less Than"), StubUI(point=34.2))
    await app._check_alarm(4.87925)
    assert app.sent == ["4-20mA Sensor has dropped below 34.2 L with a value of 4.88 L"]


@pytest.mark.asyncio
async def test_less_than_notification_message():
    app = StubApp(make_config(alarm_type="Less Than"), StubUI(point=500))
    await app._check_alarm(120.5)
    assert app.sent == ["4-20mA Sensor has dropped below 500 L with a value of 120.5 L"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reading, expected",
    [
        (4500, "4-20mA Sensor has exceeded 4000 L with a value of 4500 L"),
        (300, "4-20mA Sensor has dropped below 1000 L with a value of 300 L"),
    ],
)
async def test_allowed_range_reports_the_crossed_bound(reading, expected):
    app = StubApp(
        make_config(alarm_type="Allowed Range"), StubUI(alarm_range=[1000, 4000])
    )
    await app._check_alarm(reading)
    assert app.sent == [expected]


@pytest.mark.asyncio
async def test_allowed_range_handles_a_reversed_slider_value():
    app = StubApp(
        make_config(alarm_type="Allowed Range"), StubUI(alarm_range=[4000, 1000])
    )
    await app._check_alarm(300)
    assert "dropped below 1000 L" in app.sent[0]


@pytest.mark.asyncio
async def test_reading_inside_the_allowed_range_is_silent():
    app = StubApp(
        make_config(alarm_type="Allowed Range"), StubUI(alarm_range=[1000, 4000])
    )
    await app._check_alarm(2500)
    assert app.sent == []


@pytest.mark.asyncio
async def test_disabled_alarm_never_notifies():
    app = StubApp(make_config(alarm_enabled=False), StubUI(point=100))
    await app._check_alarm(9999)
    assert app.sent == []


@pytest.mark.asyncio
async def test_message_omits_units_when_none_configured():
    config = make_config()
    config.measurement_units.load_data(None)
    app = StubApp(config, StubUI(point=3000))
    await app._check_alarm(4200)
    assert app.sent == ["4-20mA Sensor has exceeded 3000 with a value of 4200"]


def test_slider_bounds_default_to_the_sensor_range():
    config = make_config()
    assert (config.alarm_slider_min, config.alarm_slider_max) == (0.0, 5000.0)


def test_slider_bounds_can_be_overridden():
    config = make_config(alarm_slider_minimum=1000.0, alarm_slider_maximum=4000.0)
    assert (config.alarm_slider_min, config.alarm_slider_max) == (1000.0, 4000.0)
