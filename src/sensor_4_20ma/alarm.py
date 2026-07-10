import logging
import time
from enum import Enum
from typing import NamedTuple

log = logging.getLogger(__name__)


class AlarmType(Enum):
    greater_than = "Greater Than"
    less_than = "Less Than"
    allowed_range = "Allowed Range"


class Direction(Enum):
    exceeded = "exceeded"
    dropped_below = "dropped below"


class Breach(NamedTuple):
    """A reading that has crossed one of its configured bounds."""

    direction: Direction
    bound: float


def evaluate(value, alarm_type, point=None, low=None, high=None) -> Breach | None:
    """Check a reading against its bounds, without regard for timing.

    ``point`` is used by the single-sided modes; ``low`` and ``high`` by
    ``allowed_range``. Returns None when the reading is within bounds, or when
    the bounds it needs have not been set yet.

    An ``allowed_range`` breach reports the bound that was actually crossed, so
    a range alarm still resolves to a single direction and a single number.
    """
    if value is None:
        return None

    if alarm_type is AlarmType.greater_than:
        if point is not None and value > point:
            return Breach(Direction.exceeded, point)
    elif alarm_type is AlarmType.less_than:
        if point is not None and value < point:
            return Breach(Direction.dropped_below, point)
    elif alarm_type is AlarmType.allowed_range:
        if high is not None and value > high:
            return Breach(Direction.exceeded, high)
        if low is not None and value < low:
            return Breach(Direction.dropped_below, low)

    return None


class Alarm:
    """Debounces breaches into notifications.

    A breach must persist for ``grace_period`` seconds before it notifies, which
    stops a reading hovering on a bound from firing on every sample. While the
    breach continues, it re-notifies every ``renotify_interval`` seconds.

    Returning within bounds clears the alarm, so the next breach notifies again
    once it has served its own grace period.
    """

    def __init__(self, grace_period: float = 30.0, renotify_interval: float = 900.0):
        self.grace_period = grace_period
        self.renotify_interval = renotify_interval

        self._breach_since = None
        self._last_notified = None
        self.active = False

    @staticmethod
    def _now() -> float:
        # monotonic, so a clock adjustment can't strand an alarm in its grace period
        return time.monotonic()

    def clear(self):
        self._breach_since = None
        self._last_notified = None
        self.active = False

    def update(self, breach: Breach | None) -> bool:
        """Feed a breach (or None). Returns True when the caller should notify."""
        if breach is None:
            if self.active:
                log.info("Alarm cleared")
            self.clear()
            return False

        now = self._now()

        if self._breach_since is None:
            self._breach_since = now
            log.debug("Breach started: %s %s", breach.direction.value, breach.bound)

        if now - self._breach_since < self.grace_period:
            return False

        if (
            self._last_notified is not None
            and now - self._last_notified < self.renotify_interval
        ):
            return False

        self.active = True
        self._last_notified = now
        return True
