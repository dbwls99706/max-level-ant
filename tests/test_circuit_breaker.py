"""
CircuitBreaker 단위 테스트
"""
from datetime import datetime, timezone, timedelta

from services.stock_service import CircuitBreaker


class TestCircuitBreaker:
    """서킷 브레이커 테스트"""

    def test_initial_state_closed(self):
        cb = CircuitBreaker()
        assert cb.is_open() is False

    def test_failure_threshold_opens_circuit(self):
        """연속 실패 시 서킷 열림"""
        cb = CircuitBreaker()
        for _ in range(CircuitBreaker.FAILURE_THRESHOLD):
            cb.record_failure()
        assert cb.is_open() is True

    def test_success_closes_circuit(self):
        """성공 시 서킷 닫힘"""
        cb = CircuitBreaker()
        for _ in range(CircuitBreaker.FAILURE_THRESHOLD):
            cb.record_failure()
        assert cb.is_open() is True

        cb.record_success()
        assert cb.is_open() is False

    def test_recovery_timeout(self):
        """복구 타임아웃 후 HALF_OPEN으로 전환"""
        cb = CircuitBreaker()
        for _ in range(CircuitBreaker.FAILURE_THRESHOLD):
            cb.record_failure()
        assert cb.is_open() is True

        # 복구 타임아웃 이후로 시간 조작
        old_time = datetime.now(timezone.utc) - timedelta(seconds=CircuitBreaker.RECOVERY_TIMEOUT + 1)
        cb._last_failure_time = old_time

        # HALF_OPEN: 한 번 시도 허용
        assert cb.is_open() is False

    def test_below_threshold_stays_closed(self):
        """임계값 미만 실패는 서킷 열지 않음"""
        cb = CircuitBreaker()
        for _ in range(CircuitBreaker.FAILURE_THRESHOLD - 1):
            cb.record_failure()
        assert cb.is_open() is False

    def test_thread_safety(self):
        """스레드 안전성 (락 확인)"""
        import threading
        cb = CircuitBreaker()
        errors = []

        def cause_failures():
            try:
                for _ in range(10):
                    cb.record_failure()
                    cb.is_open()
                    cb.record_success()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=cause_failures) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
