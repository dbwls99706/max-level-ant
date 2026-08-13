"""
CircuitBreaker 단위 테스트
"""

import threading

import pytest

from utils.resilience import CircuitBreaker, CircuitOpenError, CircuitState


def _fail(cb: CircuitBreaker, times: int = 1):
    """일반 요청 실패를 times회 기록"""
    for _ in range(times):
        permit = cb.acquire()
        assert permit is not None
        permit.failure()
        cb.release(permit)


def _succeed(cb: CircuitBreaker):
    """일반 요청 성공을 1회 기록"""
    permit = cb.acquire()
    assert permit is not None
    cb.release(permit)


def _open_circuit(cb: CircuitBreaker):
    """임계값만큼 실패시켜 서킷을 연다"""
    _fail(cb, cb.failure_threshold)
    assert cb.state == CircuitState.OPEN


def _expire_recovery_timeout(cb: CircuitBreaker):
    """복구 타임아웃이 이미 지난 것처럼 만든다"""
    cb._opened_at -= cb.recovery_timeout + 1


class TestStateTransitions:
    """상태 전이"""

    def test_initial_state_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.acquire() is not None

    def test_failure_threshold_opens_circuit(self):
        """연속 실패 시 서킷 열림"""
        cb = CircuitBreaker()
        _open_circuit(cb)
        assert cb.acquire() is None

    def test_below_threshold_stays_closed(self):
        """임계값 미만 실패는 서킷 열지 않음"""
        cb = CircuitBreaker()
        _fail(cb, cb.failure_threshold - 1)
        assert cb.state == CircuitState.CLOSED

    def test_success_resets_failure_count(self):
        """성공하면 실패 카운트가 초기화되어 다시 임계값을 채워야 열린다"""
        cb = CircuitBreaker()
        _fail(cb, cb.failure_threshold - 1)
        _succeed(cb)

        _fail(cb, cb.failure_threshold - 1)
        assert cb.state == CircuitState.CLOSED

    def test_recovery_timeout_moves_to_half_open(self):
        """복구 타임아웃 후 HALF_OPEN으로 전환"""
        cb = CircuitBreaker()
        _open_circuit(cb)
        _expire_recovery_timeout(cb)

        permit = cb.acquire()
        assert permit is not None
        assert permit.is_probe is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_probe_success_closes_circuit(self):
        """복구 프로브 성공 → CLOSED"""
        cb = CircuitBreaker()
        _open_circuit(cb)
        _expire_recovery_timeout(cb)

        permit = cb.acquire()
        cb.release(permit)
        assert cb.state == CircuitState.CLOSED

    def test_half_open_probe_failure_reopens_circuit(self):
        """복구 프로브 실패 → 즉시 OPEN, 타임아웃 재시작"""
        cb = CircuitBreaker()
        _open_circuit(cb)
        _expire_recovery_timeout(cb)

        permit = cb.acquire()
        permit.failure()
        cb.release(permit)

        assert cb.state == CircuitState.OPEN
        # 타임아웃이 다시 시작됐으므로 곧바로는 통과하지 못한다
        assert cb.acquire() is None


class TestStaleOutcomes:
    """
    뒤늦게 도착한 결과가 상태 머신을 우회하지 못해야 한다.

    ThreadPoolExecutor로 KIS 요청을 병렬 처리하므로, CLOSED일 때 출발한 요청이
    서킷이 열린 뒤에 끝나는 상황이 실제로 발생한다.
    """

    def test_stale_success_does_not_close_open_circuit(self):
        """
        CLOSED에서 출발한 요청의 뒤늦은 성공이 OPEN을 닫아서는 안 된다.

        시나리오 (임계값 1):
          1. A, B 모두 CLOSED에서 허가증을 받는다
          2. A가 먼저 500으로 끝난다 → OPEN
          3. B가 나중에 200으로 끝난다
          4. B의 성공은 무시돼야 한다 (복구 타임아웃·프로브를 건너뛸 수 없다)
        """
        cb = CircuitBreaker(failure_threshold=1)

        permit_a = cb.acquire()
        permit_b = cb.acquire()
        assert permit_a is not None and permit_b is not None
        assert permit_b.is_probe is False

        permit_a.failure()
        cb.release(permit_a)
        assert cb.state == CircuitState.OPEN

        cb.release(permit_b)  # 뒤늦은 성공
        assert cb.state == CircuitState.OPEN, "뒤늦은 성공이 서킷을 닫았습니다"
        assert cb.acquire() is None, "복구 타임아웃 없이 트래픽이 풀렸습니다"

    def test_stale_success_via_guard(self):
        """guard()를 쓰는 실제 호출 경로에서도 동일하게 무시된다"""
        cb = CircuitBreaker(failure_threshold=1)

        slow_permit = cb.acquire()  # CLOSED에서 출발한 느린 요청

        with cb.guard() as call:  # 빠른 요청이 먼저 실패
            call.failure()
        assert cb.state == CircuitState.OPEN

        cb.release(slow_permit)  # 느린 요청이 뒤늦게 성공
        assert cb.state == CircuitState.OPEN

    def test_only_probe_success_closes_circuit(self):
        """OPEN을 닫을 수 있는 것은 HALF_OPEN 프로브의 성공뿐이다"""
        cb = CircuitBreaker(failure_threshold=1)
        stale_permit = cb.acquire()

        _fail(cb, 1)
        assert cb.state == CircuitState.OPEN

        cb.release(stale_permit)  # 일반 요청 성공 → 무시
        assert cb.state == CircuitState.OPEN

        _expire_recovery_timeout(cb)
        probe = cb.acquire()
        assert probe.is_probe is True
        cb.release(probe)  # 프로브 성공 → 닫힘
        assert cb.state == CircuitState.CLOSED

    def test_stale_failure_does_not_disturb_probe(self):
        """
        CLOSED에서 출발한 요청의 뒤늦은 실패가 진행 중인 복구 프로브를
        무효화해서는 안 된다.
        """
        cb = CircuitBreaker(failure_threshold=1)
        stale_permit = cb.acquire()

        _fail(cb, 1)
        assert cb.state == CircuitState.OPEN
        _expire_recovery_timeout(cb)

        probe = cb.acquire()
        assert probe.is_probe is True

        stale_permit.failure()
        cb.release(stale_permit)  # 낡은 실패 → 무시
        assert cb.state == CircuitState.HALF_OPEN

        cb.release(probe)  # 프로브 성공 → 정상적으로 닫힘
        assert cb.state == CircuitState.CLOSED

    def test_stale_success_after_full_recovery_cycle(self):
        """
        서킷이 열렸다가 정상 복구된 뒤 도착한 낡은 성공은
        실패 카운터를 건드리지 않는다 (세대가 다르므로 무시).
        """
        cb = CircuitBreaker(failure_threshold=2)
        stale_permit = cb.acquire()

        _fail(cb, 2)
        _expire_recovery_timeout(cb)
        probe = cb.acquire()
        cb.release(probe)
        assert cb.state == CircuitState.CLOSED

        # 새 세대에서 실패 1건 누적
        _fail(cb, 1)
        # 낡은 성공이 도착해도 이 카운터를 초기화하면 안 된다
        cb.release(stale_permit)
        _fail(cb, 1)
        assert cb.state == CircuitState.OPEN, "낡은 성공이 실패 카운터를 초기화했습니다"

    def test_concurrent_mixed_outcomes_keep_circuit_open(self):
        """
        여러 스레드가 동시에 진행 중일 때, 실패로 서킷이 열린 뒤 도착하는
        성공들이 서킷을 다시 열어두지 못하게 해야 한다.
        """
        cb = CircuitBreaker(failure_threshold=1)

        permits = [cb.acquire() for _ in range(16)]
        assert all(p is not None for p in permits)

        failing, succeeding = permits[0], permits[1:]
        failing.failure()
        cb.release(failing)
        assert cb.state == CircuitState.OPEN

        release_all = threading.Barrier(len(succeeding))

        def worker(permit):
            release_all.wait()
            cb.release(permit)

        threads = [threading.Thread(target=worker, args=(p,)) for p in succeeding]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert cb.state == CircuitState.OPEN
        assert cb.acquire() is None


class TestHalfOpenSingleProbe:
    """HALF_OPEN에서 복구 프로브는 한 건만 통과해야 한다"""

    def test_only_one_probe_allowed(self):
        """프로브가 결과를 기록하기 전까지 후속 요청은 차단"""
        cb = CircuitBreaker()
        _open_circuit(cb)
        _expire_recovery_timeout(cb)

        assert cb.acquire() is not None  # 프로브 1건 통과
        assert cb.acquire() is None  # 결과 기록 전에는 추가 통과 없음
        assert cb.acquire() is None

    def test_probe_slot_released_on_success(self):
        cb = CircuitBreaker()
        _open_circuit(cb)
        _expire_recovery_timeout(cb)

        cb.release(cb.acquire())
        # CLOSED가 됐으므로 이후 요청은 자유롭게 통과
        assert cb.acquire() is not None
        assert cb.acquire() is not None

    def test_concurrent_probes_only_one_wins(self):
        """여러 스레드가 동시에 진입해도 외부 호출은 1건만 나가야 한다"""
        cb = CircuitBreaker()
        _open_circuit(cb)
        _expire_recovery_timeout(cb)

        start = threading.Barrier(20)
        allowed = []
        allowed_lock = threading.Lock()

        def worker():
            start.wait()
            if cb.acquire() is not None:
                with allowed_lock:
                    allowed.append(1)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(allowed) == 1, f"프로브가 {len(allowed)}건 통과했습니다"

    def test_probe_failure_blocks_next_wave(self):
        """프로브가 실패하면 다음 요청 무리는 다시 전부 차단"""
        cb = CircuitBreaker()
        _open_circuit(cb)
        _expire_recovery_timeout(cb)

        probe = cb.acquire()
        probe.failure()
        cb.release(probe)

        assert all(cb.acquire() is None for _ in range(10))


class TestGuard:
    """guard() 컨텍스트 매니저"""

    def test_guard_records_success_by_default(self):
        cb = CircuitBreaker()
        _fail(cb, cb.failure_threshold - 1)

        with cb.guard():
            pass

        # 실패 카운트가 초기화됐는지 확인
        _fail(cb, cb.failure_threshold - 1)
        assert cb.state == CircuitState.CLOSED

    def test_guard_records_explicit_failure(self):
        cb = CircuitBreaker()
        for _ in range(cb.failure_threshold):
            with cb.guard() as call:
                call.failure()
        assert cb.state == CircuitState.OPEN

    def test_guard_records_failure_on_exception(self):
        cb = CircuitBreaker()
        for _ in range(cb.failure_threshold):
            with pytest.raises(RuntimeError):
                with cb.guard():
                    raise RuntimeError("API 장애")
        assert cb.state == CircuitState.OPEN

    def test_guard_raises_when_open(self):
        cb = CircuitBreaker()
        _open_circuit(cb)
        with pytest.raises(CircuitOpenError):
            with cb.guard():
                pytest.fail("서킷이 열려 있으면 블록이 실행되면 안 된다")

    def test_guard_releases_probe_on_early_return(self):
        """블록 안에서 return으로 빠져나가도 프로브 슬롯이 반납된다"""
        cb = CircuitBreaker()
        _open_circuit(cb)
        _expire_recovery_timeout(cb)

        def probe():
            with cb.guard() as call:
                call.failure()
                return "early"

        assert probe() == "early"
        assert cb.state == CircuitState.OPEN

        # 슬롯이 반납됐으므로 타임아웃 경과 후 다시 프로브가 가능해야 한다
        _expire_recovery_timeout(cb)
        assert cb.acquire() is not None

    def test_guard_releases_probe_on_exception(self):
        cb = CircuitBreaker()
        _open_circuit(cb)
        _expire_recovery_timeout(cb)

        with pytest.raises(RuntimeError):
            with cb.guard():
                raise RuntimeError("타임아웃")

        assert cb.state == CircuitState.OPEN
        _expire_recovery_timeout(cb)
        assert cb.acquire() is not None

    def test_double_release_is_safe(self):
        """같은 허가증을 두 번 반납해도 상태가 이중 반영되지 않는다"""
        cb = CircuitBreaker(failure_threshold=2)
        permit = cb.acquire()
        permit.failure()
        cb.release(permit)
        cb.release(permit)  # 두 번째는 무시돼야 한다
        assert cb.state == CircuitState.CLOSED


class TestThreadSafety:
    def test_no_errors_under_contention(self):
        """스레드 안전성 (락 확인)"""
        cb = CircuitBreaker()
        errors = []

        def hammer():
            try:
                for _ in range(20):
                    permit = cb.acquire()
                    if permit is not None:
                        cb.release(permit)
            except Exception as e:  # pragma: no cover - 실패 시에만 도달
                errors.append(e)

        threads = [threading.Thread(target=hammer) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
