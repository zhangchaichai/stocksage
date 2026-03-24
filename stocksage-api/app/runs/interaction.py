"""InteractionRequest: asyncio.Event-based wait/respond pattern.

Supports pausing workflow execution at an interaction node, waiting for
user response via the REST API, and auto-continuing on timeout.

Used by RunOrchestrator to implement Human-in-the-Loop in streaming workflows.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class InteractionRequest:
    """A pending interaction request.

    The workflow blocks on ``wait_for_response()`` until a user calls
    ``deliver_response()`` via the REST API, or the timeout expires.
    """

    run_id: str
    prompt: str
    options: list[str] = field(default_factory=list)
    timeout: float = 120.0  # seconds

    _event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    _response: str | None = field(default=None, repr=False)

    async def wait_for_response(self) -> str | None:
        """Block until response is delivered or timeout expires.

        Returns:
            User response string, or None if timeout (auto-continue).
        """
        try:
            await asyncio.wait_for(self._event.wait(), timeout=self.timeout)
            return self._response
        except asyncio.TimeoutError:
            logger.info(
                "Interaction timeout for run %s after %.0fs, auto-continuing",
                self.run_id, self.timeout,
            )
            return None

    def deliver_response(self, response: str) -> None:
        """Deliver a user response, unblocking the waiting coroutine.

        Args:
            response: The user's response text.
        """
        self._response = response
        self._event.set()

    @property
    def is_pending(self) -> bool:
        """Whether this interaction is still waiting for a response."""
        return not self._event.is_set()


class InteractionManager:
    """Manages pending interactions across all active runs."""

    def __init__(self) -> None:
        self._pending: dict[str, InteractionRequest] = {}

    def create(
        self,
        run_id: str,
        prompt: str,
        options: list[str] | None = None,
        timeout: float = 120.0,
    ) -> InteractionRequest:
        """Create a new interaction request for a run.

        Args:
            run_id: The run ID.
            prompt: The prompt to show to the user.
            options: Optional list of predefined response options.
            timeout: Timeout in seconds before auto-continuing.

        Returns:
            InteractionRequest instance.
        """
        req = InteractionRequest(
            run_id=run_id,
            prompt=prompt,
            options=options or [],
            timeout=timeout,
        )
        self._pending[run_id] = req
        return req

    def get_pending(self, run_id: str) -> InteractionRequest | None:
        """Get the pending interaction for a run, if any."""
        req = self._pending.get(run_id)
        if req and req.is_pending:
            return req
        return None

    def respond(self, run_id: str, response: str) -> bool:
        """Deliver a response to a pending interaction.

        Args:
            run_id: The run ID.
            response: User response text.

        Returns:
            True if response was delivered, False if no pending interaction.
        """
        req = self.get_pending(run_id)
        if req is None:
            return False
        req.deliver_response(response)
        self._pending.pop(run_id, None)
        return True

    def cleanup(self, run_id: str) -> None:
        """Remove interaction state for a completed run."""
        self._pending.pop(run_id, None)
