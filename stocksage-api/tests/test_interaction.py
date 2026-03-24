"""InteractionRequest and InteractionManager tests."""

from __future__ import annotations

import asyncio

import pytest

from app.runs.interaction import InteractionManager, InteractionRequest


class TestInteractionRequest:
    @pytest.mark.asyncio
    async def test_wait_and_respond(self):
        """Response delivered before timeout unblocks wait."""
        req = InteractionRequest(
            run_id="test-run-1",
            prompt="确认继续？",
            options=["继续", "取消"],
            timeout=5.0,
        )

        async def deliver_later():
            await asyncio.sleep(0.1)
            req.deliver_response("继续")

        asyncio.create_task(deliver_later())
        result = await req.wait_for_response()

        assert result == "继续"
        assert not req.is_pending

    @pytest.mark.asyncio
    async def test_timeout_returns_none(self):
        """Timeout without response returns None."""
        req = InteractionRequest(
            run_id="test-run-2",
            prompt="确认？",
            timeout=0.1,
        )

        result = await req.wait_for_response()
        assert result is None

    @pytest.mark.asyncio
    async def test_is_pending(self):
        """is_pending reflects current state."""
        req = InteractionRequest(
            run_id="test-run-3",
            prompt="确认？",
            timeout=5.0,
        )
        assert req.is_pending is True

        req.deliver_response("ok")
        assert req.is_pending is False


class TestInteractionManager:
    def test_create_and_get(self):
        mgr = InteractionManager()
        req = mgr.create("run-1", "test prompt", ["a", "b"])

        pending = mgr.get_pending("run-1")
        assert pending is req
        assert pending.prompt == "test prompt"
        assert pending.options == ["a", "b"]

    def test_get_nonexistent_returns_none(self):
        mgr = InteractionManager()
        assert mgr.get_pending("nonexistent") is None

    def test_respond_delivers(self):
        mgr = InteractionManager()
        mgr.create("run-1", "confirm?")

        ok = mgr.respond("run-1", "yes")
        assert ok is True

        # After delivery, no more pending
        assert mgr.get_pending("run-1") is None

    def test_respond_no_pending(self):
        mgr = InteractionManager()
        ok = mgr.respond("run-1", "yes")
        assert ok is False

    def test_cleanup(self):
        mgr = InteractionManager()
        mgr.create("run-1", "test")
        mgr.cleanup("run-1")

        assert mgr.get_pending("run-1") is None

    def test_multiple_runs_isolated(self):
        mgr = InteractionManager()
        mgr.create("run-1", "prompt-1")
        mgr.create("run-2", "prompt-2")

        assert mgr.get_pending("run-1").prompt == "prompt-1"
        assert mgr.get_pending("run-2").prompt == "prompt-2"

        mgr.respond("run-1", "answer-1")
        assert mgr.get_pending("run-1") is None
        assert mgr.get_pending("run-2") is not None
