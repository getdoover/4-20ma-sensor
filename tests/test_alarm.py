"""Tests for the alarm evaluation and notification debouncing."""

import pytest

from sensor_4_20ma.alarm import Alarm, AlarmType, Direction, evaluate


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
