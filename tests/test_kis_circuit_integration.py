"""
KIS API 클라이언트 × 서킷 브레이커 통합 테스트

단위 테스트(test_circuit_breaker.py)가 브레이커 자체의 상태 전이를 검증한다면,
여기서는 실제 호출 경로가 브레이커를 올바르게 사용하는지를 검증한다.
- 서킷이 열리면 HTTP 호출 자체가 나가지 않는다
- HALF_OPEN 복구 프로브는 동시 요청이 몰려도 1건만 외부로 나간다
- 캐시된 토큰 반환 경로가 프로브 슬롯을 잡아먹지 않는다
- 병렬 요청 중 뒤늦게 도착한 성공이 열린 서킷을 되돌리지 않는다
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from services import stock_service
from services.stock_service import KISAPIClient
from utils.resilience import CircuitState


class FakeResponse:
    """requests.Response 최소 스텁"""

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


@pytest.fixture
def breaker():
    """테스트마다 깨끗한 서킷 브레이커 상태로 시작"""
    stock_service._circuit_breaker.reset()
    yield stock_service._circuit_breaker
    stock_service._circuit_breaker.reset()


@pytest.fixture
def valid_token():
    """유효한 토큰이 캐시된 상태 (토큰 발급 HTTP 호출이 끼어들지 않게)"""
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


def _open_circuit(breaker):
    for _ in range(breaker.failure_threshold):
        permit = breaker.acquire()
        assert permit is not None
        permit.failure()
        breaker.release(permit)


def _expire_recovery_timeout(breaker):
    breaker._opened_at -= breaker.recovery_timeout + 1


class TestCircuitBlocksCalls:
    def test_open_circuit_skips_http_call(self, breaker, valid_token):
        """서킷이 열려 있으면 시세 조회 HTTP 요청이 나가지 않는다"""
        _open_circuit(breaker)

        with patch.object(stock_service._http, "get") as mock_get:
            assert KISAPIClient.get_stock_price("005930") is None
            mock_get.assert_not_called()

    def test_http_error_opens_circuit(self, breaker, valid_token):
        """HTTP 에러가 임계값만큼 쌓이면 서킷이 열린다"""
        with patch.object(
            stock_service._http,
            "get",
            return_value=FakeResponse(500, {"msg_cd": "EGW00201", "msg1": "초당 초과"}),
        ):
            for _ in range(breaker.failure_threshold):
                assert KISAPIClient.get_stock_price("005930") is None

        assert breaker.state == CircuitState.OPEN

    def test_data_not_found_does_not_open_circuit(self, breaker, valid_token):
        """rt_cd != 0 (종목 없음)은 API 장애가 아니므로 서킷을 열지 않는다"""
        with patch.object(
            stock_service._http,
            "get",
            return_value=FakeResponse(
                200, {"rt_cd": "1", "msg1": "조회할 자료가 없습니다"}
            ),
        ):
            for _ in range(breaker.failure_threshold * 2):
                assert KISAPIClient.get_stock_price("999999") is None

        assert breaker.state == CircuitState.CLOSED


class TestStaleOutcome:
    """
    StockService는 ThreadPoolExecutor로 시세를 병렬 조회한다(batch_get_prices).
    그래서 CLOSED일 때 출발한 요청이 서킷이 열린 뒤에 끝나는 상황이 실제로 발생한다.
    """

    def test_slow_success_does_not_reopen_traffic(self, breaker, valid_token):
        """
        느린 200 응답이 뒤늦게 도착해도 서킷은 열린 채로 유지돼야 한다.

        예전 구현은 `record_success()`가 상태와 무관하게 CLOSED로 되돌려서,
        복구 타임아웃도 HALF_OPEN 프로브도 건너뛰고 트래픽이 전부 풀렸다.
        """
        slow_started = threading.Event()
        slow_release = threading.Event()

        def fake_get(url, headers=None, params=None, timeout=None):
            if params["FID_INPUT_ISCD"] == "005930":
                slow_started.set()
                slow_release.wait(timeout=5)  # 서킷이 열릴 때까지 붙잡아 둔다
                return FakeResponse(200, PRICE_OK)
            return FakeResponse(500, {"msg_cd": "EGW00201", "msg1": "장애"})

        with patch.object(stock_service._http, "get", side_effect=fake_get):
            with ThreadPoolExecutor(max_workers=2) as executor:
                slow = executor.submit(KISAPIClient.get_stock_price, "005930")
                assert slow_started.wait(timeout=5), "느린 요청이 시작되지 않았습니다"

                # 그 사이 빠른 실패들이 서킷을 연다
                for _ in range(breaker.failure_threshold):
                    assert KISAPIClient.get_stock_price("000001") is None
                assert breaker.state == CircuitState.OPEN

                # 이제 느린 요청이 200으로 끝난다
                slow_release.set()
                assert slow.result(timeout=5) is not None

        assert breaker.state == CircuitState.OPEN, "뒤늦은 성공이 서킷을 닫았습니다"

        # 복구 타임아웃 전이므로 여전히 HTTP 호출이 나가면 안 된다
        with patch.object(stock_service._http, "get") as mock_get:
            assert KISAPIClient.get_stock_price("005930") is None
            mock_get.assert_not_called()


class TestRecoveryProbe:
    def test_only_one_probe_call_goes_out(self, breaker, valid_token):
        """HALF_OPEN에서 동시 요청이 몰려도 외부 호출은 1건만 나간다"""
        _open_circuit(breaker)
        _expire_recovery_timeout(breaker)

        call_count = 0
        count_lock = threading.Lock()
        release_probe = threading.Event()
        thread_count = 12
        ready = threading.Barrier(thread_count)

        def slow_get(*args, **kwargs):
            nonlocal call_count
            with count_lock:
                call_count += 1
            # 프로브가 결과를 기록하기 전에 다른 스레드들이 진입하도록 붙잡아 둔다
            release_probe.wait(timeout=5)
            return FakeResponse(200, PRICE_OK)

        results = []
        results_lock = threading.Lock()

        def worker():
            ready.wait()
            result = KISAPIClient.get_stock_price("005930")
            with results_lock:
                results.append(result)

        with patch.object(stock_service._http, "get", side_effect=slow_get):
            threads = [threading.Thread(target=worker) for _ in range(thread_count)]
            for t in threads:
                t.start()

            # 프로브가 요청을 보낸 뒤, 나머지 스레드가 차단되는 것을 확인하고 해제
            deadline = threading.Event()
            deadline.wait(0.3)
            assert call_count == 1, f"복구 프로브가 {call_count}건 나갔습니다"

            release_probe.set()
            for t in threads:
                t.join(timeout=5)

        # 프로브가 성공했으므로 서킷은 닫힌다
        assert breaker.state == CircuitState.CLOSED
        # 차단된 요청들은 None을 받는다 (프로브만 시세를 받음)
        assert results.count(None) == thread_count - 1

    def test_failed_probe_reopens_circuit(self, breaker, valid_token):
        """복구 프로브가 실패하면 서킷은 다시 닫히지 않고 열린 상태로 돌아간다"""
        _open_circuit(breaker)
        _expire_recovery_timeout(breaker)

        with patch.object(
            stock_service._http, "get", return_value=FakeResponse(503, {})
        ) as mock_get:
            assert KISAPIClient.get_stock_price("005930") is None
            assert mock_get.call_count == 1

        assert breaker.state == CircuitState.OPEN

        # 타임아웃이 재시작됐으므로 곧바로는 프로브가 나가지 않는다
        with patch.object(stock_service._http, "get") as mock_get:
            assert KISAPIClient.get_stock_price("005930") is None
            mock_get.assert_not_called()

    def test_successful_probe_closes_circuit(self, breaker, valid_token):
        """복구 프로브가 성공하면 서킷이 닫히고 이후 요청이 정상 통과한다"""
        _open_circuit(breaker)
        _expire_recovery_timeout(breaker)

        with patch.object(
            stock_service._http, "get", return_value=FakeResponse(200, PRICE_OK)
        ):
            result = KISAPIClient.get_stock_price("005930")

        assert result is not None
        assert result["price"] == 70500
        assert breaker.state == CircuitState.CLOSED


class TestTokenPath:
    def test_cached_token_does_not_consume_probe_slot(self, breaker, valid_token):
        """
        캐시된 토큰을 반환하는 경로는 서킷을 건드리지 않아야 한다.

        예전 구현은 토큰 캐시 히트 경로에서도 서킷을 통과 판정해,
        HALF_OPEN 프로브 슬롯을 잡고도 결과를 기록하지 않는 문제가 있었다.
        """
        _open_circuit(breaker)
        _expire_recovery_timeout(breaker)

        # 토큰은 캐시 히트 (HTTP 호출 없음)
        assert KISAPIClient.get_access_token() == "test-token"
        # 프로브 슬롯이 소모되지 않았으므로 여전히 OPEN 상태
        assert breaker.state == CircuitState.OPEN

        # 실제 시세 조회가 복구 프로브를 가져간다
        with patch.object(
            stock_service._http, "get", return_value=FakeResponse(200, PRICE_OK)
        ) as mock_get:
            assert KISAPIClient.get_stock_price("005930") is not None
            assert mock_get.call_count == 1

        assert breaker.state == CircuitState.CLOSED
