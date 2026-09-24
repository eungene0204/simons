"""Share an in-flight computation without sharing subscriber cancellation or results."""
from __future__ import annotations

import contextvars
import copy
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

import cancellation


@dataclass
class _Flight:
    done: threading.Event = field(default_factory=threading.Event)
    token: cancellation.CancelToken = field(default_factory=cancellation.CancelToken)
    subscribers: int = 0
    stage: str | None = None
    result: Any = None
    error: BaseException | None = None


class SingleFlight:
    def __init__(self):
        self._lock = threading.Lock()
        self._flights: dict[str, _Flight] = {}

    def run(self, key: str, compute: Callable, on_stage=None):
        cancellation.raise_if_cancelled()
        with self._lock:
            flight = self._flights.get(key)
            owner = flight is None
            if owner:
                flight = self._flights[key] = _Flight()
            flight.subscribers += 1
        if owner:
            context = contextvars.copy_context()

            def work():
                try:
                    with cancellation.bind(flight.token):
                        flight.result = compute(lambda stage: setattr(flight, "stage", stage))
                except BaseException as exc:
                    flight.error = exc
                finally:
                    with self._lock:
                        flight.done.set()
                        if self._flights.get(key) is flight:
                            del self._flights[key]

            threading.Thread(target=context.run, args=(work,), daemon=True,
                             name="strategy-singleflight").start()
        emitted = None
        try:
            while True:
                cancellation.raise_if_cancelled()
                stage = flight.stage
                if on_stage and stage is not None and stage != emitted:
                    on_stage(stage)
                    emitted = stage
                if flight.done.wait(0.025):
                    cancellation.raise_if_cancelled()
                    if flight.error is not None:
                        raise flight.error
                    return copy.deepcopy(flight.result)
        finally:
            with self._lock:
                flight.subscribers -= 1
                abandoned = not flight.subscribers and not flight.done.is_set()
                if abandoned and self._flights.get(key) is flight:
                    del self._flights[key]
            if abandoned:
                flight.token.cancel()
