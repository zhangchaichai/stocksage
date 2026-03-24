"""ResponseBuffer tests."""

from __future__ import annotations

from app.runs.buffer import ResponseBuffer


class TestBufferAccumulation:
    def test_chunk_events_accumulate(self):
        buf = ResponseBuffer()
        events = buf.process({
            "event": "skill_chunk",
            "skill_name": "analyst",
            "payload": "Hello ",
        })
        assert len(events) == 1
        assert events[0]["item_id"]  # has stable ID
        item_id = events[0]["item_id"]

        events2 = buf.process({
            "event": "skill_chunk",
            "skill_name": "analyst",
            "payload": "World",
        })
        assert len(events2) == 1
        assert events2[0]["item_id"] == item_id  # same ID

    def test_flush_on_immediate_event(self):
        buf = ResponseBuffer()
        buf.process({"event": "skill_chunk", "skill_name": "analyst", "payload": "Hello "})
        buf.process({"event": "skill_chunk", "skill_name": "analyst", "payload": "World"})

        events = buf.process({"event": "skill_completed", "skill_name": "analyst"})
        # Should get: [skill_paragraph, skill_completed]
        assert len(events) == 2
        assert events[0]["event"] == "skill_paragraph"
        assert events[0]["payload"] == "Hello World"
        assert events[1]["event"] == "skill_completed"

    def test_no_flush_for_empty_buffer(self):
        buf = ResponseBuffer()
        events = buf.process({"event": "skill_completed", "skill_name": "analyst"})
        assert len(events) == 1
        assert events[0]["event"] == "skill_completed"

    def test_multiple_skills_isolated(self):
        buf = ResponseBuffer()
        buf.process({"event": "skill_chunk", "skill_name": "analyst_a", "payload": "A"})
        buf.process({"event": "skill_chunk", "skill_name": "analyst_b", "payload": "B"})

        events = buf.process({"event": "skill_completed", "skill_name": "analyst_a"})
        assert len(events) == 2  # paragraph + completed
        assert events[0]["payload"] == "A"

        # analyst_b still buffered
        events2 = buf.process({"event": "skill_completed", "skill_name": "analyst_b"})
        assert len(events2) == 2
        assert events2[0]["payload"] == "B"

    def test_passthrough_unknown_events(self):
        buf = ResponseBuffer()
        events = buf.process({"event": "heartbeat", "run_id": "123"})
        assert len(events) == 1
        assert events[0]["event"] == "heartbeat"

    def test_flush_all(self):
        buf = ResponseBuffer()
        buf.process({"event": "skill_chunk", "skill_name": "a", "payload": "X"})
        buf.process({"event": "skill_chunk", "skill_name": "b", "payload": "Y"})
        events = buf.flush_all()
        assert len(events) == 2
        payloads = {e["payload"] for e in events}
        assert payloads == {"X", "Y"}

    def test_chunk_does_not_mutate_original(self):
        buf = ResponseBuffer()
        original = {"event": "skill_chunk", "skill_name": "a", "payload": "X"}
        events = buf.process(original)
        # Original should not have item_id added
        assert "item_id" not in original
        assert "item_id" in events[0]
