"""Tests for the alarm evaluation and notification debouncing."""

import pytest

from sensor_4_20ma.alarm import Alarm, AlarmGate, AlarmType, Direction, evaluate


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def advance(self, seconds):
        self.now += seconds

    def __call__(self):
        return self.now


@pytest.fixture
def alarm():
    a = Alarm(grace_period=30.0, renotify_interval=900.0)
    a._now = FakeClock()
    return a


def test_greater_than():
    breach = evaluate(85, AlarmType.greater_than, point=80)
    assert breach == (Direction.exceeded, 80)
    assert evaluate(80, AlarmType.greater_than, point=80) is None
    assert evaluate(75, AlarmType.greater_than, point=80) is None


def test_less_than():
    breach = evaluate(15, AlarmType.less_than, point=20)
    assert breach == (Direction.dropped_below, 20)
    assert evaluate(20, AlarmType.less_than, point=20) is None
    assert evaluate(25, AlarmType.less_than, point=20) is None


def test_allowed_range_reports_the_bound_that_was_crossed():
    assert evaluate(95, AlarmType.allowed_range, low=20, high=80) == (
        Direction.exceeded,
        80,
    )
    assert evaluate(5, AlarmType.allowed_range, low=20, high=80) == (
        Direction.dropped_below,
        20,
    )
    assert evaluate(50, AlarmType.allowed_range, low=20, high=80) is None


def test_no_breach_without_bounds_or_reading():
    assert evaluate(85, AlarmType.greater_than, point=None) is None
    assert evaluate(None, AlarmType.greater_than, point=80) is None
    assert evaluate(85, AlarmType.allowed_range, low=None, high=None) is None


def test_grace_period_must_elapse_before_notifying(alarm):
    breach = evaluate(85, AlarmType.greater_than, point=80)

    assert alarm.update(breach) is False
    alarm._now.advance(29)
    assert alarm.update(breach) is False

    alarm._now.advance(2)
    assert alarm.update(breach) is True
    assert alarm.active is True


def test_does_not_renotify_until_the_interval_elapses(alarm):
    breach = evaluate(85, AlarmType.greater_than, point=80)

    alarm.update(breach)
    alarm._now.advance(31)
    assert alarm.update(breach) is True

    alarm._now.advance(899)
    assert alarm.update(breach) is False

    alarm._now.advance(2)
    assert alarm.update(breach) is True


def test_returning_in_bounds_clears_the_alarm(alarm):
    breach = evaluate(85, AlarmType.greater_than, point=80)

    alarm.update(breach)
    alarm._now.advance(31)
    assert alarm.update(breach) is True

    assert alarm.update(None) is False
    assert alarm.active is False

    # a fresh breach serves its own grace period rather than notifying instantly
    assert alarm.update(breach) is False
    alarm._now.advance(31)
    assert alarm.update(breach) is True


def test_briefly_crossing_the_bound_never_notifies(alarm):
    breach = evaluate(85, AlarmType.greater_than, point=80)

    assert alarm.update(breach) is False
    alarm._now.advance(5)
    assert alarm.update(None) is False

    alarm._now.advance(100)
    # the earlier breach must not count toward this one's grace period
    assert alarm.update(breach) is False


# --------------------------------------------------------------------------
# alarm_renotify_interval_s <= 0 means "never re-notify"
# --------------------------------------------------------------------------
@pytest.mark.parametrize("interval", [0.0, -5.0])
def test_renotify_interval_of_zero_or_less_notifies_once(interval):
    alarm = Alarm(grace_period=30.0, renotify_interval=interval)
    alarm._now = FakeClock()
    breach = evaluate(85, AlarmType.greater_than, point=80)

    alarm.update(breach)
    alarm._now.advance(31)
    assert alarm.update(breach) is True

    # every later sample of the same alarm stays quiet, however long it lasts
    for _ in range(10):
        alarm._now.advance(3600)
        assert alarm.update(breach) is False
    assert alarm.active is True


def test_renotify_zero_still_notifies_a_fresh_alarm_after_clearing():
    alarm = Alarm(grace_period=0.0, renotify_interval=0.0)
    alarm._now = FakeClock()
    breach = evaluate(85, AlarmType.greater_than, point=80)

    assert alarm.update(breach) is True
    assert alarm.update(breach) is False
    alarm.update(None)
    assert alarm.update(breach) is True


# --------------------------------------------------------------------------
# AlarmGate
# --------------------------------------------------------------------------
@pytest.fixture
def gate():
    g = AlarmGate(threshold=300.0, delay=30.0)
    g._now = FakeClock()
    return g


def test_gate_arms_only_after_the_delay(gate):
    assert gate.update(1500) is False
    assert gate.remaining() == 30.0
    gate._now.advance(29)
    assert gate.update(1500) is False
    gate._now.advance(1)
    assert gate.update(1500) is True
    assert gate.armed is True
    assert gate.remaining() == 0.0


def test_gate_dip_restarts_the_delay(gate):
    gate.update(1500)
    gate._now.advance(25)
    assert gate.update(300) is False  # at the threshold is not above it
    gate._now.advance(1)
    assert gate.update(1500) is False
    gate._now.advance(29)
    assert gate.update(1500) is False
    gate._now.advance(1)
    assert gate.update(1500) is True


def test_gate_disarms_immediately_when_the_signal_drops(gate):
    gate.update(1500)
    gate._now.advance(30)
    assert gate.update(1500) is True
    assert gate.update(0) is False
    assert gate.armed is False


@pytest.mark.parametrize("signal", [None, "not a number", [1]])
def test_gate_treats_an_unknown_signal_as_disarmed(gate, signal):
    gate.update(1500)
    gate._now.advance(30)
    assert gate.update(1500) is True
    assert gate.update(signal) is False


def test_gate_with_no_delay_arms_at_once():
    gate = AlarmGate(threshold=300.0, delay=0.0)
    assert gate.update(301) is True


def test_gate_accepts_a_boolean_tag_with_the_default_threshold():
    gate = AlarmGate()
    assert gate.update(True) is True
    assert gate.update(False) is False


def test_gate_accepts_a_numeric_string():
    assert AlarmGate(threshold=300.0).update("450.5") is True
