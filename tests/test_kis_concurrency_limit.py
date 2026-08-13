"""
KIS 동시 호출 상한 테스트

CallThrottle은 호출이 '시작되는 간격'만 제어하므로, 상류가 느려지면 이미
시작된 호출이 계속 쌓인다. 요청 예산이 끝나 응답을 먼저 돌려줘도
(executor.shutdown(wait=False)) 그 worker와 소켓은 백그라운드에 남는다.
BoundedConcurrency는 '동시에 떠 있는 호출 수' 자체에 상한을 건다.

검증:
  - 동시 요청이 몰려도 in-flight 호출 수가 상한을 넘지 않는다
  - 슬롯 대기가 요청 예산을 넘기면 HTTP 호출을 시작하지 않는다
  - 예외·타임아웃·서킷 차단 어느 경로로든 슬롯이 반드시 반납된다
"""

import threading
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from services import stock_service
from services.stock_service import KISAPIClient
from settings import KISConfig
from utils import budget
from utils.resilience import BoundedConcurrency, ConcurrencyLimitError


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        return self._payload


PRICE_OK = {
    "rt_cd": "0",
    "output": {
        "hts_kor_isnm": "삼성전자",
        "stck_prpr": "70500",
        "prdy_ctrt": "1.23",
        "stck_oprc": "70000",
        "stck_hgpr": "71000",
        "stck_lwpr": "69800",
        "acml_vol": "1000000",
    },
}


def _wait_until(predicate, timeout=5.0, interval=0.02) -> bool:
    """조건이 참이 될 때까지 폴링 (고정 sleep보다 안정적)"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


@pytest.fixture(autouse=True)
def clean_state():
    stock_service._circuit_breaker.reset()
    stock_service._kis_limiter.reset_peak()
    yield
    stock_service._circuit_breaker.reset()
    # 앞 테스트의 worker가 남아 다음 테스트의 in_flight 단정을 오염시키지 않도록
    # 슬롯이 모두 반납될 때까지 기다린다.
    assert _wait_until(lambda: stock_service._kis_limiter.in_flight == 0), (
        f"테스트 종료 후에도 슬롯 {stock_service._kis_limiter.in_flight}개가 남아 있다"
    )


@pytest.fixture
def valid_token():
    prev_token = KISAPIClient._access_token
    prev_expiry = KISAPIClient._token_expires_at
    KISAPIClient._access_token = "test-token"
    KISAPIClient._token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    with (
        patch.object(stock_service.KISConfig, "APP_KEY", "key"),
        patch.object(stock_service.KISConfig, "APP_SECRET", "secret"),
    ):
        yield
    KISAPIClient._access_token = prev_token
    KISAPIClient._token_expires_at = prev_expiry


class TestBoundedConcurrencyPrimitive:
    def test_never_exceeds_limit(self):
        limiter = BoundedConcurrency(3)
        release = threading.Event()
        entered = threading.Semaphore(0)

        def worker():
            try:
                with limiter.slot(timeout=5):
                    entered.release()
                    release.wait(timeout=5)
            except ConcurrencyLimitError:
                pass

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()

        # 상한만큼 진입할 때까지 기다린 뒤 관측
        for _ in range(3):
            assert entered.acquire(timeout=5)
        time.sleep(0.2)
        assert limiter.in_flight == 3
        assert limiter.peak_in_flight == 3, (
            f"동시 실행이 상한을 넘었다: {limiter.peak_in_flight}"
        )

        release.set()
        for t in threads:
            t.join(timeout=5)
        assert limiter.in_flight == 0, "슬롯이 반납되지 않았다"

    def test_slot_released_on_exception(self):
        limiter = BoundedConcurrency(1)
        with pytest.raises(RuntimeError):
            with limiter.slot(timeout=1):
                raise RuntimeError("호출 실패")
        assert limiter.in_flight == 0
        # 다시 잡을 수 있어야 한다
        with limiter.slot(timeout=1):
            pass

    def test_zero_timeout_does_not_wait(self):
        limiter = BoundedConcurrency(1)
        with limiter.slot(timeout=1):
            started = time.monotonic()
            with pytest.raises(ConcurrencyLimitError):
                with limiter.slot(timeout=0):
                    pytest.fail("슬롯이 없는데 진입했다")
            assert time.monotonic() - started < 0.1

    def test_timeout_raises_without_leaking(self):
        limiter = BoundedConcurrency(1)
        with limiter.slot(timeout=1):
            with pytest.raises(ConcurrencyLimitError):
                with limiter.slot(timeout=0.05):
                    pytest.fail("슬롯이 없는데 진입했다")
        # 바깥 슬롯 반납 후에는 정상 확보
        assert limiter.in_flight == 0
        with limiter.slot(timeout=1):
            pass


class TestKisCallsRespectLimit:
    def test_concurrent_price_lookups_stay_under_limit(self, valid_token):
        """동시 시세 조회가 몰려도 in-flight KIS 호출은 상한 이하여야 한다"""
        limit = KISConfig.MAX_CONCURRENT_CALLS
        release = threading.Event()
        observed = []
        obs_lock = threading.Lock()

        def slow_get(url, headers=None, params=None, timeout=None):
            with obs_lock:
                observed.append(stock_service._kis_limiter.in_flight)
            release.wait(timeout=5)
            return FakeResponse(200, PRICE_OK)

        stock_service.StockService._price_cache.clear()
        thread_count = limit * 3

        def worker(i):
            KISAPIClient.get_stock_price(f"00000{i % 10}")

        with patch.object(stock_service.requests, "get", side_effect=slow_get):
            threads = [
                threading.Thread(target=worker, args=(i,)) for i in range(thread_count)
            ]
            for t in threads:
                t.start()
            try:
                # 상한만큼 채워질 때까지 기다린 뒤 관측
                _wait_until(
                    lambda: stock_service._kis_limiter.in_flight >= limit, timeout=3
                )
                in_flight_now = stock_service._kis_limiter.in_flight
            finally:
                release.set()
                for t in threads:
                    t.join(timeout=10)

        assert in_flight_now <= limit, f"동시 호출 {in_flight_now}건 > 상한 {limit}"
        assert stock_service._kis_limiter.peak_in_flight <= limit, (
            f"관측된 최대 동시 호출 {stock_service._kis_limiter.peak_in_flight} "
            f"> 상한 {limit}"
        )
        assert observed, "실제 HTTP 호출이 한 건도 일어나지 않았다"
        assert stock_service._kis_limiter.in_flight == 0, "슬롯이 누수됐다"

    def test_budget_exhausted_while_waiting_skips_http_call(self, valid_token):
        """
        슬롯을 기다리는 동안 예산이 끝나면 HTTP 호출을 시작하지 않아야 한다.
        (기다렸다 호출해봐야 카카오는 이미 타임아웃)
        """
        call_count = 0
        count_lock = threading.Lock()
        release = threading.Event()

        def slow_get(url, headers=None, params=None, timeout=None):
            nonlocal call_count
            with count_lock:
                call_count += 1
            release.wait(timeout=5)
            return FakeResponse(200, PRICE_OK)

        stock_service.StockService._price_cache.clear()
        limit = KISConfig.MAX_CONCURRENT_CALLS

        # 상한만큼 슬롯을 붙잡아 둔다
        holders = []
        with patch.object(stock_service.requests, "get", side_effect=slow_get):
            try:
                for i in range(limit):
                    t = threading.Thread(
                        target=lambda idx=i: KISAPIClient.get_stock_price(f"11111{idx}")
                    )
                    t.start()
                    holders.append(t)

                # throttle(호출 간 최소 간격) 때문에 시작에 시간이 걸리므로 폴링한다
                assert _wait_until(lambda: call_count == limit), (
                    f"선점 호출이 상한만큼 시작되지 않았다 ({call_count}/{limit})"
                )

                # 예산이 거의 없는 요청은 슬롯을 기다리지 않고 포기해야 한다
                started = time.monotonic()
                with budget.request_budget(0.35):
                    result = KISAPIClient.get_stock_price("999999")
                waited = time.monotonic() - started

                assert result is None
                assert call_count == limit, (
                    f"예산이 없는데 HTTP 호출을 시작했다 (호출 {call_count}건)"
                )
                assert waited < 1.5, f"예산 대비 과도하게 대기했다: {waited:.2f}초"
            finally:
                # 단정이 실패해도 worker를 반드시 풀어준다
                # (안 그러면 다음 테스트의 in_flight 단정이 오염된다)
                release.set()
                for t in holders:
                    t.join(timeout=10)

        assert stock_service._kis_limiter.in_flight == 0, "슬롯이 누수됐다"

    def test_slot_released_when_circuit_open(self, valid_token):
        """서킷이 열려 호출이 차단돼도 슬롯은 반납돼야 한다"""
        breaker = stock_service._circuit_breaker
        for _ in range(breaker.failure_threshold):
            permit = breaker.acquire()
            permit.failure()
            breaker.release(permit)

        for _ in range(KISConfig.MAX_CONCURRENT_CALLS * 2):
            assert KISAPIClient.get_stock_price("005930") is None

        assert stock_service._kis_limiter.in_flight == 0, (
            "서킷 차단 경로에서 슬롯이 누수됐다"
        )

    def test_slot_released_on_request_exception(self, valid_token):
        """네트워크 예외가 나도 슬롯은 반납돼야 한다"""

        def boom(url, headers=None, params=None, timeout=None):
            raise stock_service.RequestException("네트워크 끊김")

        stock_service.StockService._price_cache.clear()
        with patch.object(stock_service.requests, "get", side_effect=boom):
            for _ in range(KISConfig.MAX_CONCURRENT_CALLS * 2):
                assert KISAPIClient.get_stock_price("005930") is None

        assert stock_service._kis_limiter.in_flight == 0, (
            "예외 경로에서 슬롯이 누수됐다"
        )
