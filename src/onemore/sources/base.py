from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Protocol, runtime_checkable

from ..model import Session


@runtime_checkable
class Source(Protocol):
    name: str

    def fetch_sessions(self, since: datetime | None = None) -> Iterable[Session]: ...


@runtime_checkable
class Sink(Protocol):
    """Optional capability: push a rendered week into the logging app as a routine."""

    def push_plan(self, week) -> None: ...
