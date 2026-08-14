"""
요청 시간 예산(협조적 budget) 테스트

카카오 스킬은 5초 안에 응답해야 한다. 여기서 검증하는 것은
**예산을 조회하는 경로들이 남은 예산을 지키는지**다.

검증 범위:
  - 외부 HTTP 호출 timeout에 남은 예산이 반영된다
  - 예산 소진 시 새 호출을 시작하지 않는다
  - 유량 제한 대기가 예산을 넘기지 않는다
  - 워커 스레드로 deadline이 전파된다
  - 배치 조회가 timeout 후 실행 중인 worker 종료를 기다리지 않는다

검증하지 않는 것 (구현상 보장되지 않음):
  - DB 쿼리 실행 시간
  - requests timeout의 wall-clock 총량 (connect/read 각각에 적용됨)
  → utils/budget.py 모듈 docstring 참고
"""

import threading
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from services import stock_service
from services.stock_service import KISAPIClient, StockService
from settings import KISConfig, SkillConfig
from utils import budget
from utils.resilience import CallThrottle


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


@pytest.fixture(autouse=True)
def clean_breaker():
    stock_service._circuit_breaker.reset()
    yield
    stock_service._circuit_breaker.reset()


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


class TestSlaConfiguration:
    def test_budget_is_under_kakao_timeout(self):
        """응답 예산은 카카오 타임아웃(5초)보다 짧아야 한다"""
        assert SkillConfig.RESPONSE_BUDGET < SkillConfig.KAKAO_TIMEOUT

    def test_single_api_timeout_fits_in_budget(self):
        """
        한 요청에서 토큰 발급 + 실제 조회가 연달아 일어나도
        개별 타임아웃 합이 예산을 넘지 않아야 한다.
        """
        worst_case = KISConfig.API_TIMEOUT * 2
        assert worst_case <= SkillConfig.RESPONSE_BUDGET, (
            f"토큰({KISConfig.API_TIMEOUT}s) + 조회({KISConfig.API_TIMEOUT}s)가 "
            f"예산({SkillConfig.RESPONSE_BUDGET}s)을 초과한다"
        )


class TestDeadline:
    def test_timeout_shrinks_with_remaining_budget(self):
        """개별 호출 타임아웃은 남은 예산을 넘지 않는다"""
        with budget.request_budget(0.5):
            assert budget.timeout_for(10.0) <= 0.5

    def test_no_budget_uses_call_cap(self):
        """예산 컨텍스트 밖에서는 호출 자체 상한을 그대로 쓴다"""
        assert budget.timeout_for(7.0) == 7.0
        assert budget.exhausted(1.0) is False

    def test_exhausted_after_budget_spent(self):
        with budget.request_budget(0.05):
            time.sleep(0.06)
            assert budget.exhausted() is True
            assert budget.timeout_for(10.0) == 0.0

    def test_budget_is_restored_after_context(self):
        with budget.request_budget(1.0):
            assert budget.current_deadline() is not None
        assert budget.current_deadline() is None


class TestKisRespectsBudget:
    def test_request_timeout_is_capped_by_budget(self, valid_token):
        """requests에 넘기는 timeout이 남은 예산으로 줄어든다"""
        captured = {}

        def fake_get(url, headers=None, params=None, timeout=None):
            captured["timeout"] = timeout
            return FakeResponse(200, PRICE_OK)

        with patch.object(stock_service._http, "get", side_effect=fake_get):
            with budget.request_budget(1.0):
                KISAPIClient.get_stock_price("005930")

        # timeout은 (연결, 응답 대기) 튜플이다 - 합이 곧 벽시계 상한
        assert sum(captured["timeout"]) <= 1.0
        assert sum(captured["timeout"]) <= KISConfig.API_TIMEOUT

    def test_exhausted_budget_skips_http_call(self, valid_token):
        """예산이 남지 않으면 아예 호출하지 않는다 (카카오는 이미 타임아웃)"""
        with patch.object(stock_service._http, "get") as mock_get:
            with budget.request_budget(0.01):
                time.sleep(0.02)
                assert KISAPIClient.get_stock_price("005930") is None
            mock_get.assert_not_called()

    def test_batch_propagates_deadline_to_workers(self, valid_token):
        """
        배치 조회는 ThreadPoolExecutor를 쓴다. 워커 스레드는 deadline을
        자동으로 물려받지 않으므로 명시 전달이 동작하는지 확인한다.
        """
        seen = []

        def fake_get(url, headers=None, params=None, timeout=None):
            seen.append(budget.current_deadline())
            return FakeResponse(200, PRICE_OK)

        StockService._price_cache.clear()
        with patch.object(stock_service._http, "get", side_effect=fake_get):
            with budget.request_budget(2.0):
                StockService.batch_get_prices({"005930", "000660"})

        assert seen, "배치 조회가 실제 호출을 하지 않았다"
        assert all(dl is not None for dl in seen), (
            "워커 스레드에 요청 deadline이 전달되지 않았다"
        )

    def test_batch_timeout_does_not_wait_for_running_workers(self, valid_token):
        """
        배치 대기 시간이 끝나면 실행 중인 worker를 기다리지 않고 반환해야 한다.

        ThreadPoolExecutor를 with로 쓰면 블록 탈출 시 shutdown(wait=True)라
        as_completed에 timeout을 걸어도 실행 중 worker가 끝날 때까지 붙잡힌다.
        (수정 전에는 예산 0.8초에 worker 2초면 2.2초가 걸렸다)
        """
        worker_seconds = 2.0

        def slow_get(url, headers=None, params=None, timeout=None):
            time.sleep(worker_seconds)
            raise stock_service.Timeout("느린 서버")

        StockService._price_cache.clear()
        started = time.monotonic()
        with patch.object(stock_service._http, "get", side_effect=slow_get):
            with budget.request_budget(0.8):
                StockService.batch_get_prices({"005930", "000660", "035420"})
        elapsed = time.monotonic() - started

        assert elapsed < worker_seconds, (
            f"배치 조회가 {elapsed:.2f}초 걸렸다 — "
            f"실행 중인 worker({worker_seconds}초) 종료를 기다리고 있다"
        )

    def test_repeated_calls_stay_within_budget(self, valid_token):
        """
        외부 API가 응답하지 않아도 KIS 호출 반복은 예산 안에서 멈춰야 한다.
        (예전에는 개별 타임아웃 10초라 1회 호출로도 카카오 5초를 넘겼다)

        주의: 이건 KIS 호출 경로에 대한 검증이지 /skill의 hard SLA 보장이 아니다.
        """

        def hanging_get(url, headers=None, params=None, timeout=None):
            # 실제 소켓 타임아웃처럼 timeout 만큼 기다렸다 실패
            time.sleep(min(sum(timeout), 5.0))
            raise stock_service.Timeout("서버 무응답")

        StockService._price_cache.clear()
        started = time.monotonic()
        with patch.object(stock_service._http, "get", side_effect=hanging_get):
            with budget.request_budget(SkillConfig.RESPONSE_BUDGET):
                for _ in range(5):  # 여러 번 시도해도
                    KISAPIClient.get_stock_price("005930")
        elapsed = time.monotonic() - started

        assert elapsed < SkillConfig.KAKAO_TIMEOUT, (
            f"요청 처리에 {elapsed:.2f}초 — 카카오 타임아웃 "
            f"{SkillConfig.KAKAO_TIMEOUT}초를 넘겼다"
        )


class TestThrottleRespectsBudget:
    def test_throttle_gives_up_when_wait_exceeds_budget(self):
        """유량 제한 대기만으로 예산을 다 쓰지 않는다"""
        throttle = CallThrottle(min_interval=5.0)
        assert throttle.wait() is True  # 첫 호출은 즉시 통과

        started = time.monotonic()
        assert throttle.wait(max_wait=0.05) is False  # 5초 대기는 포기
        assert time.monotonic() - started < 1.0

    def test_throttle_still_serializes_without_budget(self):
        """예산 제한이 없으면 기존대로 간격을 지킨다"""
        throttle = CallThrottle(min_interval=0.05)
        assert throttle.wait() is True
        started = time.monotonic()
        assert throttle.wait() is True
        assert time.monotonic() - started >= 0.04

    def test_throttle_slot_not_reserved_when_declined(self):
        """대기를 포기한 호출은 슬롯을 예약하지 않는다"""
        throttle = CallThrottle(min_interval=1.0)
        throttle.wait()
        throttle.wait(max_wait=0.0)  # 거절
        # 거절된 호출이 슬롯을 잡지 않았으므로 다음 허용 시각은 그대로다
        elapsed_before = throttle._next_allowed_at
        throttle.wait(max_wait=0.0)
        assert throttle._next_allowed_at == elapsed_before


class TestConcurrentRequestsAreIsolated:
    def test_each_thread_has_own_budget(self):
        """요청별 예산은 스레드마다 독립적이어야 한다"""
        results = {}

        def worker(name, seconds):
            with budget.request_budget(seconds):
                time.sleep(0.05)
                results[name] = budget.remaining()

        threads = [
            threading.Thread(target=worker, args=("short", 0.2)),
            threading.Thread(target=worker, args=("long", 5.0)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results["short"] < results["long"]


class TestSkillEndpointBudget:
    """
    /skill 엔드포인트 자체를 호출해 예산이 실제로 걸리는지 확인한다.
    (기존 테스트는 KIS 메서드만 반복 호출해서 엔드포인트 경로를 못 봤다)
    """

    def test_skill_endpoint_applies_budget_to_handler(self, monkeypatch, skill_key):
        from fastapi.testclient import TestClient

        import main

        seen = {}

        def fake_handle(self):
            # 핸들러 실행 시점에 요청 deadline이 살아 있어야 한다
            dl = budget.current_deadline()
            seen["deadline"] = dl
            seen["remaining"] = dl.remaining() if dl else None
            return main.KakaoResponse.simple_text("ok")

        monkeypatch.setattr(main.CommandHandler, "handle", fake_handle)

        with TestClient(main.app) as client:
            resp = client.post(
                "/skill",
                json={
                    "userRequest": {
                        "user": {"id": "budgettester"},
                        "utterance": "/잔고",
                    }
                },
                headers=skill_key,
            )

        assert resp.status_code == 200
        assert seen["deadline"] is not None, "/skill이 요청 예산을 걸지 않았다"
        assert 0 < seen["remaining"] <= SkillConfig.RESPONSE_BUDGET

    def test_skill_endpoint_does_not_block_event_loop(self, monkeypatch, skill_key):
        """동기 handler가 이벤트 루프가 아닌 워커 스레드에서 실행돼야 한다"""
        import asyncio

        from fastapi.testclient import TestClient

        import main

        seen = {}

        def fake_handle(self):
            try:
                asyncio.get_running_loop()
                seen["on_event_loop"] = True
            except RuntimeError:
                seen["on_event_loop"] = False
            return main.KakaoResponse.simple_text("ok")

        monkeypatch.setattr(main.CommandHandler, "handle", fake_handle)

        with TestClient(main.app) as client:
            client.post(
                "/skill",
                json={
                    "userRequest": {"user": {"id": "loopcheck"}, "utterance": "/잔고"}
                },
                headers=skill_key,
            )

        assert seen["on_event_loop"] is False, (
            "동기 handler가 이벤트 루프에서 실행됐다 — 다른 요청까지 멈춘다"
        )


class TestSessionPerWorkerThread:
    """
    SQLAlchemy Session은 스레드 간 공유를 전제로 하지 않는다.
    handler를 워커 스레드로 옮겼으므로 Session 생성·사용·close도
    모두 그 스레드 안에서 끝나야 한다.
    """

    def test_session_is_created_and_closed_in_handler_thread(
        self, monkeypatch, skill_key
    ):
        from fastapi.testclient import TestClient

        import main

        seen = {}
        real_session_local = main.SessionLocal

        def tracking_session_local(*args, **kwargs):
            seen["created_in"] = threading.get_ident()
            session = real_session_local(*args, **kwargs)
            real_close = session.close

            def tracked_close():
                seen["closed_in"] = threading.get_ident()
                return real_close()

            session.close = tracked_close
            return session

        def fake_handle(self):
            seen["handled_in"] = threading.get_ident()
            return main.KakaoResponse.simple_text("ok")

        monkeypatch.setattr(main, "SessionLocal", tracking_session_local)
        monkeypatch.setattr(main.CommandHandler, "handle", fake_handle)

        with TestClient(main.app) as client:
            resp = client.post(
                "/skill",
                json={
                    "userRequest": {
                        "user": {"id": "sessionthread"},
                        "utterance": "/잔고",
                    }
                },
                headers=skill_key,
            )

        assert resp.status_code == 200
        assert seen["created_in"] == seen["handled_in"], (
            "Session이 handler와 다른 스레드에서 생성됐다"
        )
        assert seen["closed_in"] == seen["handled_in"], (
            "Session이 handler와 다른 스레드에서 닫혔다"
        )
        assert seen["handled_in"] != threading.main_thread().ident, (
            "handler가 메인(이벤트 루프) 스레드에서 실행됐다"
        )
