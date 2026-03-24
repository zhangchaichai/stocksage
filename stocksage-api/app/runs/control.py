"""Run control bus: bidirectional communication between WebSocket and engine.

Each active workflow run gets a RunControl instance that allows:
- pause / resume execution
- send commands from the client to the running engine
- receive responses from the engine back to the client
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RunControl:
    """Per-run control state."""

    run_id: str
    # Event is SET when not paused; cleared when paused
    _resume_event: asyncio.Event = field(default_factory=asyncio.Event)
    # Commands from client → engine
    command_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    # Responses from engine → client (beyond DB-polled events)
    response_queue: asyncio.Queue = field(default_factory=asyncio.Queue)

    def __post_init__(self):
        self._resume_event.set()  # not paused by default

    @property
    def is_paused(self) -> bool:
        return not self._resume_event.is_set()

    def pause(self) -> None:
        """Pause the run. Engine nodes should check wait_if_paused() before executing."""
        self._resume_event.clear()
        logger.info("Run %s paused", self.run_id)

    def resume(self) -> None:
        """Resume a paused run."""
        self._resume_event.set()
        logger.info("Run %s resumed", self.run_id)

    async def wait_if_paused(self) -> None:
        """Async wait until resumed. Returns immediately if not paused."""
        if not self._resume_event.is_set():
            logger.info("Run %s waiting for resume...", self.run_id)
            await self._resume_event.wait()

    def wait_if_paused_sync(self, timeout: float | None = None) -> None:
        """Synchronous (blocking) wait until resumed. For use in thread-pool workers."""
        if not self._resume_event.is_set():
            logger.info("Run %s blocking wait for resume...", self.run_id)
            # asyncio.Event.wait() is coroutine-only, so we use threading.Event pattern
            # by polling in a simple loop
            import time
            start = time.time()
            while not self._resume_event.is_set():
                time.sleep(0.2)
                if timeout and (time.time() - start) > timeout:
                    logger.warning("Run %s pause timeout after %.1fs", self.run_id, timeout)
                    break


# Global registry of active run controls
_active_controls: dict[str, RunControl] = {}


def get_or_create(run_id: str) -> RunControl:
    """Get or create a RunControl for the given run_id."""
    if run_id not in _active_controls:
        _active_controls[run_id] = RunControl(run_id=run_id)
    return _active_controls[run_id]


def get(run_id: str) -> RunControl | None:
    """Get an existing RunControl, or None if not found."""
    return _active_controls.get(run_id)


def remove(run_id: str) -> None:
    """Remove a RunControl when the run is complete."""
    ctrl = _active_controls.pop(run_id, None)
    if ctrl:
        ctrl.resume()  # unblock any waiting threads
        logger.debug("RunControl removed for %s", run_id)
