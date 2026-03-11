"""CircuitBreaker and with_retry tests."""

from __future__ import annotations

import pytest

from stocksage.errors.handler import CircuitBreaker, with_retry


class TestCircuitBreaker:
    def test_initial_state_closed(self):
        cb = CircuitBreaker()
        assert cb.state == "CLOSED"
        assert cb.allow_request() is True

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "CLOSED"
        cb.record_failure()
        assert cb.state == "OPEN"
        assert cb.allow_request() is False

    def test_success_resets(self):
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        # Should still be CLOSED because success reset the counter.
        assert cb.state == "CLOSED"

    def test_half_open_after_recovery_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.0)
        cb.record_failure()
        assert cb.state == "OPEN" or cb.state == "HALF_OPEN"
        # With 0s timeout, next access should be HALF_OPEN.
        import time
        time.sleep(0.01)
        assert cb.state == "HALF_OPEN"
        assert cb.allow_request() is True


class TestWithRetry:
    def test_succeeds_immediately(self):
        call_count = 0

        @with_retry(max_retries=2, delay=0)
        def ok():
            nonlocal call_count
            call_count += 1
            return "done"

        assert ok() == "done"
        assert call_count == 1

    def test_retries_then_succeeds(self):
        call_count = 0

        @with_retry(max_retries=2, delay=0)
        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("fail")
            return "ok"

        assert flaky() == "ok"
        assert call_count == 2

    def test_exhausts_retries(self):
        @with_retry(max_retries=1, delay=0)
        def always_fail():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            always_fail()
