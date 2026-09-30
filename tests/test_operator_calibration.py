"""Tests for operator sensor calibration (operator_calibration.py).

Like test_app_alarm.py these borrow the real methods off
Sensor420maApplication rather than building one, which needs a device agent
connection. ui_cmds and the tags are small in-memory fakes.
"""

import math

import pytest
from pydoover.rpc import RPCError

from sensor_4_20ma.app_config import Sensor420maConfig
from sensor_4_20ma.app_ui import Sensor420maUI
from sensor_4_20ma.application import Sensor420maApplication
from sensor_4_20ma.operator_calibration import (
    RPC_PATTERN,
    OperatorCalibration,
    OperatorValue,
)
from sensor_4_20ma.sensor import Sensor420ma

CALIBRATION_TAGS = ("range_low", "range_high", "offset", "operator_calibration")


# --------------------------------------------------------------------------
# fakes
# --------------------------------------------------------------------------
class FakeTag:
    def __init__(self, store, name):
        self._store = store
        self._name = name

    def get(self):
        return self._store.values.get(self._name)

    async def set(self, value, log=False):
        self._store.values[self._name] = value
        self._store.writes.append((self._name, value))


class FakeTags:
    def __init__(self, **values):
        self.values = dict(values)
        self.writes = []

    def __getitem__(self, name):
        return FakeTag(self, name)

    def __getattr__(self, name):
        if name.startswith("_") or name in ("values", "writes"):
            raise AttributeError(name)
        return FakeTag(self, name)

    def written(self, name):
        return [v for n, v in self.writes if n == name]


class FakeUIManager:
    """ui_cmds for this app: ``values`` is what the last aggregate event
    delivered; writes (the app's ``update_channel_aggregate``, one payload
    each in ``writes``) land in ``aggregate`` and only reach ``values`` when
    :meth:`deliver` runs (the echo)."""

    def __init__(self, values=None):
        self.values = dict(values) if values is not None else {}
        self.aggregate = dict(self.values)
        self.writes = []

    def write(self, payload):
        """An aggregate update: a merge, where None deletes a key."""
        self.writes.append(dict(payload))
        for key, value in payload.items():
            if value is None:
                self.aggregate.pop(key, None)
            else:
                self.aggregate[key] = value

    def deliver(self):
        self.values = dict(self.aggregate)

    def edit(self, **values):
        """A direct change of the aggregate (not by this app)."""
        self.aggregate.update(values)
        self.deliver()


class FakePlatform:
    def __init__(self, ma=12.0):
        self.ma = ma

    async def fetch_ai(self, pin):
        return self.ma


class StubCtx:
    def __init__(self, method):
        self.method = method


class FakeAggregate:
    def __init__(self, data):
        self.data = data


class FakeDeviceAgent:
    """The device agent as setup() sees it at start-up.

    ``synced`` is what wait_for_channels_sync reports. ``aggregate`` is the
    whole ui_cmds aggregate fetch_channel_aggregate returns, or an exception
    to raise (pydoover marks the channel synced even when the seed fetch
    failed, so a True wait can still be followed by a failing fetch).
    """

    def __init__(self, synced=True, aggregate=None):
        self.synced = synced
        self.aggregate = {} if aggregate is None else aggregate

    async def wait_for_channels_sync(self, names, timeout=5, inter_wait=0.2):
        assert names == ["ui_cmds"]
        return self.synced

    async def fetch_channel_aggregate(self, channel_name):
        assert channel_name == "ui_cmds"
        if isinstance(self.aggregate, Exception):
            raise self.aggregate
        return FakeAggregate(self.aggregate)


class StubApp:
    app_key = "pressure_sensor_1"
    calibration = Sensor420maApplication.calibration
    setup = Sensor420maApplication.setup
    _await_ui_cmds_sync = Sensor420maApplication._await_ui_cmds_sync
    _set_polling_frequency = Sensor420maApplication._set_polling_frequency
    _on_polling_frequency_changed = Sensor420maApplication._on_polling_frequency_changed
    main_loop = Sensor420maApplication.main_loop
    on_calibration_value = Sensor420maApplication.on_calibration_value
    on_reset_calibration = Sensor420maApplication.on_reset_calibration

    def __init__(
        self, config, ui_values=None, tags=None, ma=12.0, filter_enabled=False
    ):
        self.config = config
        self.ui_manager = FakeUIManager(ui_values)
        self.tags = tags or FakeTags()
        self.platform_iface = FakePlatform(ma)
        self.ui_cmds_synced = ui_values is not None
        self.sensor = Sensor420ma(
            0,
            self.platform_iface,
            [config.min_range.value, config.max_range.value],
            filter_enabled=filter_enabled,
        )
        self.checked = []
        self.device_agent = FakeDeviceAgent()

    def subscribe_to_tag(self, key, callback):
        pass

    async def update_channel_aggregate(self, channel_name, data, **kwargs):
        assert channel_name == "ui_cmds"
        assert set(data) == {self.app_key}
        self.ui_manager.write(data[self.app_key])

    async def _check_alarm(self, reading):
        self.checked.append(reading)

    async def rpc(self, method, value=None):
        if method == "reset_calibration":
            return await self.on_reset_calibration(StubCtx(method), value)
        return await self.on_calibration_value(StubCtx(method), value)

    async def run(self, loops=4):
        for _ in range(loops):
            await self.main_loop()
        return self.tags.values.get("value")


def make_config(enabled=True, min_range=0.0, max_range=100.0, units="bar", **extra):
    config = Sensor420maConfig()
    data = {
        "ai_pin_number": 0,
        "input_name": "Pressure",
        "min_range": min_range,
        "max_range": max_range,
        "measurement_units": units,
        "enable_signal_filtering": False,
        "sample_rate_hz": 2.0,
        "alarm": {"alarm_enabled": False},
        **extra,
    }
    if enabled is not None:
        data["operator_calibration_enabled"] = enabled
    config._inject_deployment_config(data)
    return config


def legacy_convert(ma, low, high):
    """Sensor420ma.convert_reading exactly as it was before this feature."""
    reading = ma - 4
    if reading < 0 and reading > -0.5:
        reading = 0
    return (reading / 16) * (high - low) + low


def inject(config, **changes):
    """A deployment config change reaching the running app: pydoover
    re-injects the whole app config, it does not restart the app."""
    data = {
        "ai_pin_number": 0,
        "input_name": "Pressure",
        "min_range": config.min_range.value,
        "max_range": config.max_range.value,
        "measurement_units": config.measurement_units.value,
        "enable_signal_filtering": False,
        "sample_rate_hz": 2.0,
        "alarm": {"alarm_enabled": False},
        "operator_calibration_enabled": config.operator_calibration_enabled.value,
        **changes,
    }
    config._inject_deployment_config(data)


async def expect_error(code, coro):
    with pytest.raises(RPCError) as exc:
        await coro
    assert exc.value.code == code
    return exc.value


# --------------------------------------------------------------------------
# default off: exactly today's behaviour
# --------------------------------------------------------------------------
def test_flag_defaults_off_with_the_agreed_key():
    schema = Sensor420maConfig.to_schema()
    prop = schema["properties"]["operator_calibration_enabled"]
    assert prop["default"] is False
    assert prop["title"] == "Operator Sensor Calibration"
    assert make_config(enabled=None).operator_calibration_enabled.value is False


@pytest.mark.asyncio
@pytest.mark.parametrize("ma", [3.2, 3.8, 4.0, 7.3, 12.0, 19.99, 20.0, 21.5])
async def test_off_publishes_exactly_what_it_did_before(ma):
    config = make_config(enabled=None, min_range=-12.5, max_range=987.25)
    app = StubApp(config, ui_values={}, ma=ma)
    await app.run()

    expected = None if ma < 3.5 else legacy_convert(ma, -12.5, 987.25)
    assert app.tags.values["value"] == expected
    assert app.tags.values["raw_value"] == ma
    # only the tags the app has always written
    assert {n for n, _v in app.tags.writes} == {"value", "raw_value"}
    assert app.ui_manager.writes == []


@pytest.mark.asyncio
async def test_off_ignores_operator_values_left_in_ui_cmds():
    config = make_config(enabled=False)
    app = StubApp(config, ui_values={"range_low": 50.0, "offset": 3.0}, ma=12.0)
    assert await app.run() == 50.0
    assert not any(n in CALIBRATION_TAGS for n, _v in app.tags.writes)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["range_low", "range_high", "offset"])
async def test_off_refuses_the_rpcs(method):
    app = StubApp(make_config(enabled=False), ui_values={})
    await expect_error("UNAVAILABLE", app.rpc(method, 1.0))
    await expect_error("UNAVAILABLE", app.rpc("reset_calibration"))
    assert app.ui_manager.writes == []
    assert app.tags.writes == []


@pytest.mark.asyncio
async def test_off_clears_readbacks_left_by_an_earlier_enabled_deployment():
    tags = FakeTags(
        range_low=5.0, range_high=90.0, offset=0.0, operator_calibration=True
    )
    app = StubApp(make_config(enabled=False), ui_values={}, tags=tags)
    await app.calibration.clear_stale_tags()
    assert all(tags.values[n] is None for n in CALIBRATION_TAGS)


@pytest.mark.asyncio
async def test_off_never_enabled_writes_no_tags_at_setup():
    app = StubApp(make_config(enabled=False), ui_values={})
    await app.calibration.clear_stale_tags()
    assert app.tags.writes == []


# --------------------------------------------------------------------------
# enabled
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_enabled_without_operator_values_matches_the_config():
    config = make_config(min_range=-12.5, max_range=987.25)
    app = StubApp(config, ui_values={}, ma=7.3)
    assert await app.run() == legacy_convert(7.3, -12.5, 987.25)
    assert app.tags.values["range_low"] == -12.5
    assert app.tags.values["range_high"] == 987.25
    assert app.tags.values["offset"] == 0.0
    assert app.tags.values["operator_calibration"] is True


@pytest.mark.asyncio
async def test_values_change_the_published_value_on_the_next_reading():
    app = StubApp(make_config(), ui_values={}, ma=12.0)
    assert await app.run() == 50.0

    assert await app.rpc("range_low", 10) == {"range_low": 10.0}
    assert await app.rpc("range_high", "110") == {"range_high": 110.0}
    assert await app.run() == 60.0

    assert await app.rpc("offset", -2.5) == {"offset": -2.5}
    assert await app.run() == 57.5
    # raw_value is still the loop current in mA
    assert app.tags.values["raw_value"] == 12.0
    assert app.checked[-1] == 57.5  # alarms see the corrected value
    assert (
        app.tags.values["range_low"],
        app.tags.values["range_high"],
        app.tags.values["offset"],
    ) == (10.0, 110.0, -2.5)


@pytest.mark.asyncio
async def test_rpc_publishes_the_readback_at_once_and_persists_to_ui_cmds():
    app = StubApp(make_config(), ui_values={})
    app.calibration.restore()  # setup
    await app.rpc("range_high", 250)
    assert app.tags.values["range_high"] == 250.0
    # one aggregate write; an operator value clears the reset marker
    assert app.ui_manager.writes == [{"range_high": 250.0, "range_high_default": None}]


@pytest.mark.asyncio
async def test_unfiltered_value_uses_the_operator_values_too():
    config = make_config(enable_signal_filtering=True)
    app = StubApp(config, ui_values={}, ma=12.0, filter_enabled=True)
    await app.run()
    await app.rpc("offset", 1)
    await app.run()
    assert app.tags.values["unfiltered_value"] == 51.0


@pytest.mark.asyncio
async def test_range_change_does_not_disturb_the_filter():
    """The Kalman filter runs on mA, before the mapping: once settled, a new
    range gives the new value straight away rather than a filtered ramp."""
    config = make_config(enable_signal_filtering=True)
    app = StubApp(config, ui_values={}, ma=12.0, filter_enabled=True)
    settled = await app.run(30)
    assert settled == pytest.approx(50.0, abs=0.01)

    await app.rpc("range_high", 1000)
    assert await app.run(loops=1) == pytest.approx(500.0, abs=0.1)


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method, value",
    [
        ("range_low", "abc"),
        ("range_low", None),
        ("range_low", True),
        ("range_low", [1]),
        ("range_low", {"value": 1}),
        ("range_high", math.nan),
        ("range_high", math.inf),
        ("range_high", "-inf"),
        ("range_high", 1_000_001),
        ("range_low", -1_000_001),
        ("range_low", 100),  # == range_high
        ("range_low", 150),  # above range_high
        ("range_high", 0),  # == range_low
        ("range_high", -5),
        ("offset", 100.0001),  # outside +/- the 100 range
        ("offset", -101),
    ],
)
async def test_invalid_values_are_refused_and_change_nothing(method, value):
    app = StubApp(make_config(), ui_values={}, ma=12.0)
    await expect_error("INVALID", app.rpc(method, value))
    assert app.ui_manager.writes == []
    assert await app.run() == 50.0
    assert app.calibration.effective() == (0.0, 100.0, 0.0)


@pytest.mark.asyncio
async def test_limits_themselves_are_accepted():
    app = StubApp(make_config(), ui_values={})
    assert await app.rpc("offset", 100) == {"offset": 100.0}
    assert await app.rpc("offset", -100) == {"offset": -100.0}
    assert await app.rpc("range_high", 1e6) == {"range_high": 1e6}
    assert await app.rpc("range_low", -1e6) == {"range_low": -1e6}


@pytest.mark.asyncio
async def test_a_range_change_that_would_strand_the_offset_is_refused():
    app = StubApp(make_config(), ui_values={})
    await app.rpc("offset", 40)
    await expect_error("INVALID", app.rpc("range_high", 30))
    assert app.calibration.effective() == (0.0, 100.0, 40.0)


@pytest.mark.asyncio
async def test_floats_are_kept_to_four_decimal_places():
    app = StubApp(make_config(), ui_values={})
    assert await app.rpc("range_low", 1.23456789) == {"range_low": 1.2346}
    assert app.ui_manager.writes == [{"range_low": 1.2346, "range_low_default": None}]
    assert await app.rpc("offset", 2) == {"offset": 2.0}


def test_rpc_pattern_matches_only_the_three_values():
    for name in ("range_low", "range_high", "offset"):
        assert RPC_PATTERN.match(name)
    for name in ("range_low_x", "offsets", "reset_calibration", "alarm_point"):
        assert not RPC_PATTERN.match(name)


# --------------------------------------------------------------------------
# reset
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reset_stores_the_config_values_in_ui_cmds():
    app = StubApp(make_config(min_range=2.0, max_range=40.0), ui_values={}, ma=12.0)
    await app.rpc("range_low", 5)
    await app.rpc("offset", 1)
    app.ui_manager.deliver()
    assert await app.run() == 23.5

    result = await app.rpc("reset_calibration", True)
    assert result == {"range_low": 2.0, "range_high": 40.0, "offset": 0.0}
    # one aggregate write: each config default with its reset marker
    assert app.ui_manager.writes[-1] == {
        "range_low": 2.0,
        "range_low_default": 2.0,
        "range_high": 40.0,
        "range_high_default": 40.0,
        "offset": 0.0,
        "offset_default": 0.0,
    }
    assert await app.run() == 21.0
    app.ui_manager.deliver()  # the echo
    assert await app.run() == 21.0
    assert app.tags.values["range_low"] == 2.0
    assert all(v.setting() is None for v in app.calibration.values.values())


@pytest.mark.asyncio
async def test_after_reset_a_config_change_takes_effect_and_is_written_back():
    config = make_config(min_range=0.0, max_range=100.0)
    app = StubApp(config, ui_values={}, ma=12.0)
    await app.setup()
    await app.rpc("range_low", 5)
    app.ui_manager.deliver()
    await app.rpc("reset_calibration")
    app.ui_manager.deliver()
    assert await app.run() == 50.0
    writes = len(app.ui_manager.writes)

    # the deployment config changes under the running app
    inject(config, min_range=10.0, max_range=210.0)
    assert app.calibration.effective() == (10.0, 210.0, 0.0)
    assert await app.run(loops=1) == 110.0
    assert (app.tags.values["range_low"], app.tags.values["range_high"]) == (
        10.0,
        210.0,
    )
    # written back once (the offset default did not change) so the cloud
    # inputs show the new values, still marked as the config default
    assert app.ui_manager.writes[writes:] == [
        {
            "range_low": 10.0,
            "range_low_default": 10.0,
            "range_high": 210.0,
            "range_high_default": 210.0,
        }
    ]
    app.ui_manager.deliver()
    assert await app.run() == 110.0
    assert len(app.ui_manager.writes) == writes + 1
    assert all(v.setting() is None for v in app.calibration.values.values())

    # and it keeps following the config
    inject(config, min_range=0.0, max_range=50.0)
    assert await app.run() == 25.0


@pytest.mark.asyncio
async def test_restart_after_a_reset_and_a_config_change_uses_the_new_config():
    # reset under Max Range 100; the config is now 200
    values = {
        "range_low": 0.0,
        "range_low_default": 0.0,
        "range_high": 100.0,
        "range_high_default": 100.0,
        "offset": 0.0,
        "offset_default": 0.0,
    }
    app = StubApp(make_config(max_range=200.0), ui_values=values, ma=12.0)
    await app.setup()
    assert app.calibration.effective() == (0.0, 200.0, 0.0)
    assert await app.run() == 100.0
    assert app.ui_manager.writes == [{"range_high": 200.0, "range_high_default": 200.0}]


@pytest.mark.asyncio
async def test_setting_a_value_clears_its_marker():
    config = make_config()
    app = StubApp(config, ui_values={}, ma=12.0)
    await app.rpc("reset_calibration")
    app.ui_manager.deliver()
    assert app.ui_manager.values["range_high_default"] == 100.0

    # the same number as the default, but now an operator value
    assert await app.rpc("range_high", 100) == {"range_high": 100.0}
    assert app.ui_manager.writes[-1] == {
        "range_high": 100.0,
        "range_high_default": None,
    }
    app.ui_manager.deliver()
    assert "range_high_default" not in app.ui_manager.values
    assert app.ui_manager.values["range_low_default"] == 0.0  # others untouched
    assert app.calibration.values["range_high"].setting() == 100.0

    # so a config change no longer moves it, and nothing is written back
    inject(config, max_range=300.0)
    writes = len(app.ui_manager.writes)
    assert await app.run() == 50.0
    assert app.calibration.effective() == (0.0, 100.0, 0.0)
    assert len(app.ui_manager.writes) == writes


@pytest.mark.asyncio
async def test_direct_edit_of_a_reset_value_is_an_operator_value():
    app = StubApp(make_config(), ui_values={}, ma=12.0)
    await app.rpc("reset_calibration")
    app.ui_manager.deliver()
    assert await app.run() == 50.0
    app.ui_manager.edit(range_high=120.0)  # the marker is left at 100
    assert app.calibration.effective() == (0.0, 120.0, 0.0)
    assert await app.run() == 60.0


@pytest.mark.asyncio
async def test_offline_boot_after_a_reset_follows_the_config_once_ui_cmds_syncs():
    # the tag holds the old default (Max Range was 100 at the reset, now 200)
    tags = FakeTags(
        range_low=0.0, range_high=100.0, offset=0.0, operator_calibration=True
    )
    app = StubApp(make_config(max_range=200.0), ui_values=None, tags=tags, ma=12.0)
    app.calibration.restore()
    assert app.calibration.effective() == (0.0, 100.0, 0.0)

    # ui_cmds syncs: the value is the reset default, so the config applies
    app.ui_manager.edit(range_high=100.0, range_high_default=100.0)
    assert app.calibration.effective() == (0.0, 200.0, 0.0)
    assert await app.run() == 100.0
    assert app.ui_manager.writes == [{"range_high": 200.0, "range_high_default": 200.0}]


class FailingWritesApp(StubApp):
    """ui_cmds cannot be written (the DDA is down)."""

    async def update_channel_aggregate(self, channel_name, data, **kwargs):
        raise ConnectionError("DDA down")


@pytest.mark.asyncio
async def test_a_failed_write_changes_nothing_and_reports_it():
    app = FailingWritesApp(make_config(), ui_values={"offset": 3.0}, ma=12.0)
    app.calibration.restore()
    before = app.calibration.effective()
    for method, value in (
        ("offset", 5),
        ("range_high", 200),
        ("reset_calibration", None),
    ):
        await expect_error("UNAVAILABLE", app.rpc(method, value))
        assert app.calibration.effective() == before
    assert app.tags.writes == []
    assert await app.run() == 53.0


@pytest.mark.asyncio
async def test_reset_keeps_config_values_beyond_four_decimals_exactly():
    config = make_config(min_range=0.123456, max_range=10.0)
    app = StubApp(config, ui_values={}, ma=12.0)
    await app.rpc("range_low", 1)
    await app.rpc("reset_calibration")
    app.ui_manager.deliver()
    assert app.calibration.effective() == (0.123456, 10.0, 0.0)


@pytest.mark.asyncio
async def test_reset_works_with_a_reversed_config_range():
    # reset is not validated: it only restores what the config says
    app = StubApp(make_config(min_range=100.0, max_range=0.0), ui_values={})
    await app.rpc("reset_calibration")
    assert app.calibration.effective() == (100.0, 0.0, 0.0)


# --------------------------------------------------------------------------
# restart and ui_cmds sync
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_restart_adopts_the_values_in_ui_cmds():
    app = StubApp(
        make_config(),
        ui_values={"range_low": 10.0, "range_high": 110.0, "offset": 1.5},
        ma=12.0,
    )
    app.calibration.restore()
    assert await app.run() == 61.5
    assert app.ui_manager.writes == []


@pytest.mark.asyncio
async def test_invalid_values_in_ui_cmds_are_ignored():
    app = StubApp(
        make_config(),
        ui_values={"range_low": "junk", "range_high": math.inf, "offset": 2.0},
        ma=12.0,
    )
    assert await app.run() == 52.0


@pytest.mark.asyncio
async def test_direct_ui_cmds_edit_is_adopted():
    app = StubApp(make_config(), ui_values={}, ma=12.0)
    assert await app.run() == 50.0
    app.ui_manager.edit(offset=3.0)
    assert await app.run() == 53.0


@pytest.mark.asyncio
async def test_mixed_state_that_is_not_increasing_falls_back_to_the_config_range():
    # e.g. the config range was changed after an operator set Range Low
    app = StubApp(make_config(max_range=40.0), ui_values={"range_low": 50.0}, ma=12.0)
    assert app.calibration.effective() == (0.0, 40.0, 0.0)
    assert await app.run() == 20.0


@pytest.mark.asyncio
async def test_offline_boot_restores_the_last_values_from_the_tags():
    tags = FakeTags(
        range_low=10.0, range_high=100.0, offset=2.0, operator_calibration=True
    )
    app = StubApp(make_config(), ui_values=None, tags=tags, ma=12.0)
    assert app.ui_cmds_synced is False
    app.calibration.restore()
    assert app.calibration.effective() == (10.0, 100.0, 2.0)
    assert await app.run() == 57.0

    # ui_cmds then delivers: its values win
    app.ui_manager.edit(range_low=20.0, offset=2.0)
    assert app.calibration.effective() == (20.0, 100.0, 2.0)


@pytest.mark.asyncio
async def test_offline_restore_is_dropped_when_ui_cmds_holds_none():
    tags = FakeTags(
        range_low=10.0, range_high=100.0, offset=0.0, operator_calibration=True
    )
    app = StubApp(make_config(), ui_values=None, tags=tags)
    app.calibration.restore()
    assert app.calibration.effective() == (10.0, 100.0, 0.0)
    app.ui_manager.edit(some_other_key=1)
    assert app.calibration.effective() == (0.0, 100.0, 0.0)


@pytest.mark.asyncio
async def test_restore_does_nothing_once_ui_cmds_has_synced():
    tags = FakeTags(range_low=10.0, range_high=100.0, offset=0.0)
    app = StubApp(make_config(), ui_values={}, tags=tags)
    app.calibration.restore()
    assert app.calibration.effective() == (0.0, 100.0, 0.0)


@pytest.mark.asyncio
async def test_write_before_a_late_sync_is_kept_and_stored_again():
    app = StubApp(make_config(), ui_values=None, ma=12.0)
    await app.rpc("offset", 4)
    # ui_cmds now syncs with an older value the app had not seen
    app.ui_manager.values = {"offset": 1.0}
    app.ui_manager.aggregate = {"offset": 1.0}
    assert await app.run() == 54.0
    assert app.ui_manager.writes[-1] == {"offset": 4.0, "offset_default": None}
    app.ui_manager.deliver()
    assert await app.run() == 54.0


@pytest.mark.asyncio
async def test_an_older_echo_never_replaces_a_newer_write():
    app = StubApp(make_config(), ui_values={}, ma=12.0)
    await app.rpc("offset", 1)
    await app.rpc("offset", 2)
    # the echo of the first write arrives on its own
    app.ui_manager.values = {"offset": 1.0}
    assert await app.run() == 52.0
    app.ui_manager.deliver()
    assert await app.run() == 52.0


def test_echo_timeout_forgets_a_missed_echo(monkeypatch):
    app = StubApp(make_config(), ui_values={})
    setting = app.calibration.values["offset"]
    clock = [100.0]
    monkeypatch.setattr(
        "sensor_4_20ma.operator_calibration.time.monotonic", lambda: clock[0]
    )
    setting.stage(5.0)  # its echo never arrives
    assert setting._pending == [((5.0, None), clock[0])]
    clock[0] += OperatorValue.ECHO_TIMEOUT_SECS + 1
    app.ui_manager.edit(offset=5.0)
    assert setting.setting() == 5.0
    assert setting._pending == []


@pytest.mark.asyncio
async def test_rpc_before_setup_creates_the_calibration_on_demand():
    app = StubApp(make_config(), ui_values={})
    assert "_calibration" not in app.__dict__
    await app.rpc("offset", 1)
    assert isinstance(app.calibration, OperatorCalibration)


# --------------------------------------------------------------------------
# cloud UI
# --------------------------------------------------------------------------
async def build_ui(config):
    ui = Sensor420maUI(config, None, "pressure_sensor_1")
    await ui.setup()
    return ui


@pytest.mark.asyncio
async def test_submodule_hidden_when_off():
    ui = await build_ui(make_config(enabled=False))
    assert ui.sensor_calibration.hidden is True


@pytest.mark.asyncio
async def test_submodule_shows_config_defaults_when_on():
    ui = await build_ui(make_config(min_range=-5.0, max_range=250.0, units="psi"))
    sub = ui.sensor_calibration
    assert sub.hidden is False
    assert sub.range_low.default == -5.0
    assert sub.range_high.default == 250.0
    assert sub.offset.default == 0.0
    assert sub.range_low.display_name == "Range Low (at 4 mA) (psi)"

    schema = ui.to_schema()["children"]["sensor_calibration"]["children"]
    assert schema["range_high"]["type"] == "uiFloatInput"
    assert schema["range_high"]["currentValue"] == "$cmds.app().range_high::250.0"
    assert schema["reset_calibration"]["type"] == "uiButton"
    assert schema["reset_calibration"]["displayString"] == "Reset to configured values"


def test_calibration_elements_are_interactions_for_the_rpcs():
    ui = Sensor420maUI(make_config(), None, "pressure_sensor_1")
    names = set(ui.get_interactions())
    assert {"range_low", "range_high", "offset", "reset_calibration"} <= names


@pytest.mark.asyncio
async def test_rpc_during_the_startup_wait_is_not_overwritten_by_the_restore():
    tags = FakeTags(range_low=10.0, range_high=100.0, offset=2.0)
    app = StubApp(make_config(), ui_values=None, tags=tags)
    await app.rpc("offset", 7)
    app.calibration.restore()
    assert app.calibration.effective() == (10.0, 100.0, 7.0)
    # and the RPC left the persisted readbacks alone for the restore
    assert tags.values["range_low"] == 10.0


# --------------------------------------------------------------------------
# the flag is held from setup (review finding: live deployment config change)
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_setup_latches_the_flag():
    app = StubApp(make_config(), ui_values={})
    await app.setup()
    assert app.calibration.enabled is True
    inject(app.config, operator_calibration_enabled=False)
    assert app.config.operator_calibration_enabled.value is False
    assert app.calibration.enabled is True


@pytest.mark.asyncio
async def test_flag_turned_off_live_keeps_everything_in_step_until_restart():
    """The submodule's hidden is only set in UI setup and the sensor is built
    in setup, so the flag is too: switching it off in a running app changes
    nothing half-way (no calibration the RPCs then refuse to change, no
    stale 'enabled' readback with locked-out writes)."""
    config = make_config()
    app = StubApp(config, ui_values={}, ma=12.0)
    await app.setup()
    await app.rpc("range_high", 200)
    assert await app.run() == 100.0

    inject(config, operator_calibration_enabled=False)
    assert await app.run() == 100.0
    assert app.tags.values["operator_calibration"] is True
    assert app.tags.values["range_high"] == 200.0
    # the readback says enabled, and writes are accepted to match
    assert await app.rpc("offset", 1) == {"offset": 1.0}
    assert await app.run() == 101.0

    # the next start (the same tags and ui_cmds) is exactly the legacy app
    app.ui_manager.deliver()
    restarted = StubApp(config, ui_values=app.ui_manager.values, tags=app.tags, ma=12.0)
    await restarted.setup()
    assert restarted.calibration.enabled is False
    assert all(app.tags.values[n] is None for n in CALIBRATION_TAGS)
    assert await restarted.run() == legacy_convert(12.0, 0.0, 100.0)
    await expect_error("UNAVAILABLE", restarted.rpc("offset", 2))


@pytest.mark.asyncio
async def test_flag_turned_on_live_stays_off_until_restart():
    config = make_config(enabled=False)
    app = StubApp(config, ui_values={}, ma=12.0)
    await app.setup()
    inject(config, operator_calibration_enabled=True)
    await expect_error("UNAVAILABLE", app.rpc("range_high", 200))
    assert await app.run() == 50.0
    assert not any(n in CALIBRATION_TAGS for n, _v in app.tags.writes)


def test_rpc_before_setup_reads_the_config():
    app = StubApp(make_config(enabled=False), ui_values={})
    assert app.calibration.enabled is False
    inject(app.config, operator_calibration_enabled=True)
    assert app.calibration.enabled is True


# --------------------------------------------------------------------------
# offset read from ui_cmds is checked too (review finding)
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_offset_outside_the_range_in_ui_cmds_is_not_applied():
    app = StubApp(make_config(), ui_values={"offset": 5000.0}, ma=12.0)
    assert await app.run() == 50.0
    assert app.calibration.effective() == (0.0, 100.0, 0.0)
    assert app.tags.values["offset"] == 0.0


@pytest.mark.asyncio
async def test_offset_stranded_by_a_smaller_config_range_falls_back():
    # an operator set offset 40 under a 0..100 range, then the config range
    # became 0..30 (range_low / range_high never set by an operator)
    app = StubApp(make_config(max_range=30.0), ui_values={"offset": 40.0}, ma=12.0)
    assert app.calibration.effective() == (0.0, 30.0, 0.0)
    assert await app.run() == 15.0


@pytest.mark.asyncio
async def test_offset_checked_against_the_operator_range_in_effect():
    app = StubApp(
        make_config(),
        ui_values={"range_low": 0.0, "range_high": 1000.0, "offset": 500.0},
        ma=12.0,
    )
    assert app.calibration.effective() == (0.0, 1000.0, 500.0)
    assert await app.run() == 1000.0


@pytest.mark.asyncio
async def test_an_offset_rpc_fixes_an_invalid_stored_offset():
    app = StubApp(make_config(), ui_values={"offset": 5000.0}, ma=12.0)
    assert await app.rpc("offset", 5) == {"offset": 5.0}
    assert await app.run() == 55.0


@pytest.mark.asyncio
async def test_offset_restored_from_tags_is_checked_too():
    tags = FakeTags(range_low=0.0, range_high=100.0, offset=900.0)
    app = StubApp(make_config(), ui_values=None, tags=tags, ma=12.0)
    app.calibration.restore()
    assert app.calibration.effective() == (0.0, 100.0, 0.0)


# --------------------------------------------------------------------------
# start-up ui_cmds sync (review finding: the wait reports synced even when
# the aggregate could not be fetched)
# --------------------------------------------------------------------------
OFFLINE_TAGS = {
    "range_low": 10.0,
    "range_high": 100.0,
    "offset": 2.0,
    "operator_calibration": True,
}


@pytest.mark.asyncio
async def test_synced_but_ui_cmds_not_delivered_restores_from_the_tags():
    app = StubApp(make_config(), ui_values=None, tags=FakeTags(**OFFLINE_TAGS), ma=12.0)
    # pydoover: seed failed, channel marked synced anyway; the DDA still
    # cannot serve the aggregate
    app.device_agent = FakeDeviceAgent(
        synced=True, aggregate=ConnectionError("DDA unavailable")
    )
    await app.setup()
    assert app.ui_cmds_synced is False
    assert app.calibration.effective() == (10.0, 100.0, 2.0)
    assert await app.run() == 57.0


@pytest.mark.asyncio
async def test_not_synced_at_all_restores_from_the_tags():
    app = StubApp(make_config(), ui_values=None, tags=FakeTags(**OFFLINE_TAGS), ma=12.0)
    app.device_agent = FakeDeviceAgent(synced=False)
    await app.setup()
    assert app.ui_cmds_synced is False
    assert app.calibration.effective() == (10.0, 100.0, 2.0)


@pytest.mark.asyncio
async def test_synced_aggregate_not_yet_in_ui_manager_is_used():
    """The seed failed but the DDA serves ui_cmds by the time of the fetch
    (or the sync event is not dispatched yet): its values are used, not the
    tags, and not the config until some later aggregate event."""
    app = StubApp(make_config(), ui_values=None, tags=FakeTags(**OFFLINE_TAGS), ma=12.0)
    app.device_agent = FakeDeviceAgent(
        aggregate={
            "pressure_sensor_1": {"range_low": 20.0, "offset": 1.0},
            "other_app": {"range_low": 99.0},
        }
    )
    await app.setup()
    assert app.ui_cmds_synced is True
    assert app.ui_manager.values == {"range_low": 20.0, "offset": 1.0}
    assert app.calibration.effective() == (20.0, 100.0, 1.0)


@pytest.mark.asyncio
async def test_synced_and_empty_ui_cmds_uses_the_config_not_old_tags():
    """ui_cmds genuinely holds nothing for this app, and the tags hold the
    defaults of an older config (Min Range was 10, now 0): the config wins.
    Restoring whenever ui_manager.values is empty would bring 10 back."""
    tags = FakeTags(
        range_low=10.0, range_high=100.0, offset=0.0, operator_calibration=True
    )
    app = StubApp(make_config(), ui_values=None, tags=tags, ma=12.0)
    app.device_agent = FakeDeviceAgent(aggregate={"other_app": {"x": 1}})
    await app.setup()
    assert app.ui_cmds_synced is True
    assert app.ui_manager.values == {}
    assert app.calibration.effective() == (0.0, 100.0, 0.0)


@pytest.mark.asyncio
async def test_delivered_ui_manager_values_are_not_overwritten_by_the_fetch():
    app = StubApp(make_config(), ui_values={"offset": 3.0}, ma=12.0)
    app.device_agent = FakeDeviceAgent(aggregate={"pressure_sensor_1": {"offset": 9.0}})
    await app.setup()
    assert app.ui_manager.values == {"offset": 3.0}
