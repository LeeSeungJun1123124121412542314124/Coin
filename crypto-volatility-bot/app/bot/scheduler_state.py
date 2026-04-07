"""Scheduler state — in-memory current analysis interval."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class SchedulerState:
    interval_minutes: int | None = 60
    last_run: datetime | None = None
    consecutive_failures: int = 0

    def mark_success(self) -> None:
        self.last_run = datetime.now(timezone.utc)
        self.consecutive_failures = 0

    def mark_failure(self) -> None:
        self.consecutive_failures += 1

    def set_interval(self, interval_minutes: int | None) -> None:
        self.interval_minutes = interval_minutes


_state = SchedulerState()


def get_state() -> SchedulerState:
    return _state
