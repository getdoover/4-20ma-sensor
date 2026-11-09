"""Tests for the application's alarm wiring: bounds, messages, and notifications.

These borrow the real methods off Sensor420maApplication rather than building one,
which needs a device agent connection.
"""

import pytest
from pydoover.models import NotificationSeverity

from sensor_4_20ma.alarm import Alarm, AlarmGate
from sensor_4_20ma.app_config import Sensor420maConfig
from sensor_4_20ma.app_notifications import Sensor420maNotifications
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
        # The real declarations, bound to this stub, so the tests exercise the
        # topic and severity the app actually sends rather than a copy of them.
        self.notifications = Sensor420maNotifications("4_20ma_sensor_1", self)

    @property
    def sent(self):
        return [data["message"] for _channel, data in self.published]

    async def send_notification(self, message, **kwargs):
        self.published.append(("notifications", {"message": message, **kwargs}))

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
async def test_notification_carries_the_canonical_topic():
    """The topic is what the site filters on, per notification.

    Sending without one puts the notification in the legacy bucket, where a
    subscriber can only take every app notification or none of them. The
    string is spelled out rather than rebuilt from the declaration because it
    is a contract shared with the API and the subscription editor.
    """
    app = StubApp(make_config(), StubUI(point=3000))
    await app._check_alarm(4200.0)

    channel, payload = app.published[0]
    assert channel == "notifications"
    assert str(payload["topic"]) == "dev/applications/default/4_20ma_sensor_1/alarm"
    assert payload["severity"] is NotificationSeverity.Warn
    # No title: the server substitutes the agent's display name.
    assert payload["title"] is None


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


# --------------------------------------------------------------------------
# Optional additions: alarm gate, default setpoints, sensor fault. All off
# unless configured; the tests above run with them unset.
# --------------------------------------------------------------------------
class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def advance(self, seconds):
        self.now += seconds

    def __call__(self):
        return self.now


class FakeTag:
    def __init__(self, store, name):
        self._store = store
        self._name = name

    async def set(self, value, log=False):
        self._store.values[self._name] = value
        self._store.writes.append((self._name, value))


class FakeTags:
    def __init__(self):
        self.values = {}
        self.writes = []

    def __getattr__(self, name):
        if name.startswith("_") or name in ("values", "writes"):
            raise AttributeError(name)
        return FakeTag(self, name)


class OptionsStubApp(StubApp):
    """StubApp plus what setup() builds for the optional features."""

    _alarm_armed = Sensor420maApplication._alarm_armed
    _check_sensor_fault = Sensor420maApplication._check_sensor_fault

    def __init__(self, config, ui, tag_values=None, grace_period=0.0):
        super().__init__(config, ui)
        self.clock = FakeClock()
        self.alarm = Alarm(
            grace_period=grace_period,
            renotify_interval=config.alarm.renotify_interval.value,
        )
        self.alarm._now = self.clock
        self.alarm_gate = AlarmGate(
            threshold=config.alarm.enable_threshold.value,
            delay=config.alarm.enable_delay.value,
        )
        self.alarm_gate._now = self.clock
        self.sensor_fault_alarm = Alarm(
            grace_period=grace_period,
            renotify_interval=config.alarm.renotify_interval.value,
        )
        self.sensor_fault_alarm._now = self.clock
        self.tags = FakeTags()
        self.tag_values = dict(tag_values or {})
        self.tag_reads = []

    def get_tag(self, tag_key, app_key=None, default=None):
        self.tag_reads.append((app_key, tag_key))
        return self.tag_values.get((app_key, tag_key), default)


ENGINE_RPM = ("kensho_controller_1", "engine_rpm")


def gated_config(**alarm_overrides):
    return make_config(
        alarm_type="Allowed Range",
        alarm_enable_tag={
            "app_name": "kensho_controller_1",
            "tag_name": "engine_rpm",
        },
        alarm_enable_threshold=300.0,
        alarm_enable_delay_s=30.0,
        **alarm_overrides,
    )


# ---- defaults: nothing new happens with the new keys unset ----------------
def test_new_keys_are_optional_and_off_by_default():
    config = make_config()
    assert config.alarm_enable_tag is None
    assert config.alarm.enable_threshold.value == 0.0
    assert config.alarm.enable_delay.value == 0.0
    assert config.alarm.default_low.value is None
    assert config.alarm.default_high.value is None
    assert config.sensor_fault_alarm_enabled.value is False

    schema = Sensor420maConfig.to_schema()
    assert "sensor_fault_alarm_enabled" not in schema["required"]
    assert schema["properties"]["alarm"]["required"] == []


@pytest.mark.parametrize("blank", [None, {}])
def test_a_blank_enable_tag_is_off(blank):
    gated_config()  # config elements are shared: a blank must not inherit this
    assert make_config(alarm_enable_tag=blank).alarm_enable_tag is None


@pytest.mark.asyncio
async def test_without_the_gate_no_tag_is_read_or_written():
    app = OptionsStubApp(make_config(), StubUI(point=3000))
    await app._check_alarm(4200.0)
    assert len(app.sent) == 1
    assert app.tag_reads == []
    assert app.tags.writes == []


# ---- (a) alarm gate --------------------------------------------------------
@pytest.mark.asyncio
async def test_gate_suppresses_the_alarm_while_the_engine_is_stopped():
    app = OptionsStubApp(
        gated_config(), StubUI(alarm_range=[2.0, 10.0]), {ENGINE_RPM: 0.0}
    )
    for _ in range(5):
        app.clock.advance(60)
        await app._check_alarm(0.06)
    assert app.sent == []
    assert app.tag_reads[-1] == ENGINE_RPM
    assert app.tags.values["alarm_armed"] is False
    assert app.tags.values["alarm_status"] == (
        "Alarm disarmed (kensho_controller_1.engine_rpm not above 300)"
    )


@pytest.mark.asyncio
async def test_gate_status_uses_the_configured_reason():
    app = OptionsStubApp(
        gated_config(alarm_disarmed_reason="engine stopped"),
        StubUI(alarm_range=[2.0, 10.0]),
        {ENGINE_RPM: None},
    )
    await app._check_alarm(0.06)
    assert app.tags.values["alarm_status"] == "Alarm disarmed (engine stopped)"


@pytest.mark.asyncio
async def test_gate_arms_after_the_delay_then_alarms():
    app = OptionsStubApp(
        gated_config(), StubUI(alarm_range=[2.0, 10.0]), {ENGINE_RPM: 1500.0}
    )
    await app._check_alarm(0.06)
    assert app.sent == []
    assert app.tags.values["alarm_status"] == "Alarm arming (30 s delay)"

    app.clock.advance(29)
    await app._check_alarm(0.06)
    assert app.sent == []

    app.clock.advance(1)
    await app._check_alarm(0.06)
    assert app.sent == ["4-20mA Sensor has dropped below 2 L with a value of 0.06 L"]
    assert app.tags.values["alarm_armed"] is True
    assert app.tags.values["alarm_status"] == "Alarm armed"


@pytest.mark.asyncio
async def test_disarming_clears_an_active_alarm_without_a_notification():
    app = OptionsStubApp(
        gated_config(),
        StubUI(alarm_range=[2.0, 10.0]),
        {ENGINE_RPM: 1500.0},
        grace_period=10.0,
    )
    await app._check_alarm(0.06)
    app.clock.advance(30)
    await app._check_alarm(0.06)
    app.clock.advance(10)
    await app._check_alarm(0.06)
    assert len(app.sent) == 1
    assert app.alarm.active is True

    app.tag_values[ENGINE_RPM] = 0.0
    await app._check_alarm(0.06)
    assert app.alarm.active is False
    assert len(app.sent) == 1  # no "cleared" notification

    # re-armed: the gate delay and then the full grace period apply again
    app.tag_values[ENGINE_RPM] = 1500.0
    await app._check_alarm(0.06)
    app.clock.advance(30)
    await app._check_alarm(0.06)
    app.clock.advance(9)
    await app._check_alarm(0.06)
    assert len(app.sent) == 1
    app.clock.advance(1)
    await app._check_alarm(0.06)
    assert len(app.sent) == 2


@pytest.mark.asyncio
async def test_gate_is_ignored_while_the_alarm_is_disabled():
    app = OptionsStubApp(
        gated_config(alarm_enabled=False),
        StubUI(alarm_range=[2.0, 10.0]),
        {ENGINE_RPM: 1500.0},
    )
    await app._check_alarm(0.06)
    assert app.sent == []
    assert app.tag_reads == []


# ---- (b) default setpoints -------------------------------------------------
@pytest.mark.asyncio
async def test_default_high_seeds_an_untouched_greater_than_slider():
    app = OptionsStubApp(make_config(default_high=3000.0), StubUI())
    await app._check_alarm(4200.0)
    assert app.sent == ["4-20mA Sensor has exceeded 3000 L with a value of 4200 L"]


@pytest.mark.asyncio
async def test_default_low_seeds_an_untouched_less_than_slider():
    app = OptionsStubApp(
        make_config(alarm_type="Less Than", default_low=500.0, default_high=4000.0),
        StubUI(),
    )
    await app._check_alarm(120.5)
    assert app.sent == ["4-20mA Sensor has dropped below 500 L with a value of 120.5 L"]


@pytest.mark.asyncio
async def test_operator_slider_value_wins_over_the_default():
    app = OptionsStubApp(make_config(default_high=3000.0), StubUI(point=4500))
    await app._check_alarm(4200.0)
    assert app.sent == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reading, expected",
    [
        (4500, "4-20mA Sensor has exceeded 4000 L with a value of 4500 L"),
        (300, "4-20mA Sensor has dropped below 1000 L with a value of 300 L"),
        (2500, None),
    ],
)
async def test_default_range_seeds_an_untouched_allowed_range(reading, expected):
    app = OptionsStubApp(
        make_config(
            alarm_type="Allowed Range", default_low=1000.0, default_high=4000.0
        ),
        StubUI(),
    )
    await app._check_alarm(reading)
    assert app.sent == ([expected] if expected else [])


def test_default_range_fills_a_blank_side_with_the_slider_end():
    config = make_config(alarm_type="Allowed Range", default_high=4000.0)
    assert config.alarm_default_range == [0.0, 4000.0]
    assert make_config(alarm_type="Allowed Range").alarm_default_range is None


@pytest.mark.asyncio
async def test_ui_shows_the_default_setpoints():
    from sensor_4_20ma.app_ui import Sensor420maUI

    ui = Sensor420maUI(
        make_config(alarm_type="Allowed Range", default_low=1.5, default_high=12.0),
        None,
        "4_20ma_sensor_1",
    )
    await ui.setup()
    children = ui.to_schema()["children"]
    assert children["alarm_range"]["currentValue"] == (
        "$cmds.app().alarm_range::[1.5, 12]"
    )

    ui = Sensor420maUI(make_config(default_high=3000.0), None, "4_20ma_sensor_1")
    await ui.setup()
    assert ui.to_schema()["children"]["alarm_point"]["currentValue"] == (
        "$cmds.app().alarm_point::3000"
    )


@pytest.mark.asyncio
async def test_ui_unchanged_without_the_new_keys():
    from sensor_4_20ma.app_ui import Sensor420maUI

    ui = Sensor420maUI(make_config(alarm_type="Allowed Range"), None, "x")
    await ui.setup()
    children = ui.to_schema()["children"]
    assert children["alarm_range"]["currentValue"] == "$cmds.app().alarm_range"
    assert children["alarm_point"]["currentValue"] == "$cmds.app().alarm_point"
    assert ui.alarm_status.hidden is True
    assert ui.sensor_status.hidden is True


@pytest.mark.asyncio
async def test_ui_shows_the_status_rows_when_configured():
    from sensor_4_20ma.app_ui import Sensor420maUI

    config = gated_config()
    config.sensor_fault_alarm_enabled.load_data(True)
    ui = Sensor420maUI(config, None, "x")
    await ui.setup()
    assert ui.alarm_status.hidden is False
    assert ui.sensor_status.hidden is False


# ---- (c) sensor fault ------------------------------------------------------
@pytest.mark.asyncio
async def test_sensor_fault_notifies_after_the_grace_period():
    app = OptionsStubApp(make_config(), StubUI(), grace_period=30.0)
    await app._check_sensor_fault(0.04)
    app.clock.advance(29)
    await app._check_sensor_fault(0.04)
    assert app.sent == []
    assert app.tags.values["sensor_fault"] is True
    assert app.tags.values["sensor_status"] == "Sensor fault: 0.04 mA"

    app.clock.advance(1)
    await app._check_sensor_fault(0.04)
    assert app.sent == [
        "4-20mA Sensor sensor fault: loop current is 0.04 mA, below 3.5 mA"
    ]
    channel, payload = app.published[0]
    assert channel == "notifications"
    assert str(payload["topic"]) == (
        "dev/applications/default/4_20ma_sensor_1/sensor_fault"
    )
    assert payload["severity"] is NotificationSeverity.Warn


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", [4.06, 3.5, None])
async def test_healthy_or_unread_loop_is_not_a_fault(raw):
    app = OptionsStubApp(make_config(), StubUI())
    for _ in range(3):
        app.clock.advance(60)
        await app._check_sensor_fault(raw)
    assert app.sent == []
    assert app.tags.values["sensor_fault"] is False
    assert app.tags.values["sensor_status"] == "OK"


@pytest.mark.asyncio
async def test_sensor_fault_respects_renotify_zero():
    app = OptionsStubApp(make_config(alarm_renotify_interval_s=0.0), StubUI())
    for _ in range(5):
        app.clock.advance(3600)
        await app._check_sensor_fault(0.0)
    assert len(app.sent) == 1


# ---- (d) renotify 0 through the app ----------------------------------------
@pytest.mark.asyncio
async def test_renotify_zero_sends_one_notification_per_alarm():
    app = OptionsStubApp(make_config(alarm_renotify_interval_s=0.0), StubUI(point=3000))
    for _ in range(20):
        app.clock.advance(1)
        await app._check_alarm(4200.0)
    assert len(app.sent) == 1
