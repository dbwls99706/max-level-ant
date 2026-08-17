"""순위 조회 타임아웃 진단 검증"""

import asyncio
import logging
import time
from unittest.mock import MagicMock, patch

import pytest
import requests
from requests.exceptions import ConnectTimeout, ReadTimeout, Timeout

from services.stock_service import KISAPIClient, StockService
from settings import KISConfig

# utils.logger가 만드는 서비스 로거 이름. propagate=False라 caplog에 명시해야 한다.
SERVICE_LOGGER = "stock_king.service"


def test_rank_uses_its_own_timeout(caplog):
    """순위 조회는 단일 시세보다 넉넉한 상한을 쓴다"""
    seen = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        seen["timeout"] = timeout
        raise Timeout()

    with (
        patch.object(KISAPIClient, "_get_headers", return_value={"x": "y"}),
        patch("services.stock_service._http.get", side_effect=fake_get),
    ):
        result = KISAPIClient.get_volume_rank("J")

    assert result == []
    assert sum(seen["timeout"]) == KISConfig.RANK_TIMEOUT
    assert KISConfig.RANK_TIMEOUT > KISConfig.API_TIMEOUT, (
        "시세 상한과 같으면 의미가 없다"
    )


def test_timeout_log_shows_elapsed_and_cap(caplog):
    """'타임아웃'만 찍으면 상류가 느린 건지 우리가 좁게 준 건지 모른다"""

    def slow_then_timeout(url, headers=None, params=None, timeout=None):
        time.sleep(0.05)
        raise Timeout()

    with (
        patch.object(KISAPIClient, "_get_headers", return_value={"x": "y"}),
        patch("services.stock_service._http.get", side_effect=slow_then_timeout),
        # 서비스 로거는 propagate=False라 루트에 붙는 caplog로는 안 잡힌다.
        # 로거 이름을 명시해야 이 파일만 돌리든 전체를 돌리든 같게 동작한다.
        caplog.at_level(logging.WARNING, logger=SERVICE_LOGGER),
    ):
        KISAPIClient.get_volume_rank("J")

    msgs = [r.message for r in caplog.records if "순위 조회 타임아웃" in r.message]
    assert msgs, "타임아웃 로그가 없다"
    assert "초 대기" in msgs[0], f"실제 대기 시간이 없다: {msgs[0]}"
    assert "상한" in msgs[0], f"적용된 상한이 없다: {msgs[0]}"


class TestRankCache:
    """순위 캐시와 실패 시 폴백"""

    def setup_method(self):
        from services.stock_service import _rank_cache

        _rank_cache.clear()

    def _ok_response(self, names):
        class R:
            status_code = 200

            @staticmethod
            def json():
                return {
                    "rt_cd": "0",
                    "output": [
                        {
                            "mksc_shrn_iscd": f"00{i}",
                            "hts_kor_isnm": n,
                            "stck_prpr": "1000",
                            "prdy_ctrt": "1.5",
                            "acml_vol": "100",
                            "acml_tr_pbmn": "1000",
                        }
                        for i, n in enumerate(names)
                    ],
                }

        return R()

    def test_second_call_does_not_hit_kis(self):
        """같은 순위를 사람 수만큼 다시 물어볼 이유가 없다"""
        calls = []

        def fake_get(url, headers=None, params=None, timeout=None):
            calls.append(url)
            return self._ok_response(["삼성전자", "SK하이닉스"])

        with (
            patch.object(KISAPIClient, "_get_headers", return_value={"x": "y"}),
            patch("services.stock_service._http.get", side_effect=fake_get),
        ):
            first = KISAPIClient.get_volume_rank("J")
            second = KISAPIClient.get_volume_rank("J")

        assert first and first == second
        assert len(calls) == 1, f"KIS를 {len(calls)}번 불렀다"

    def test_different_keys_are_cached_separately(self):
        """거래량과 거래대금은 다른 데이터다"""
        calls = []

        def fake_get(url, headers=None, params=None, timeout=None):
            calls.append(params.get("FID_BLNG_CLS_CODE"))
            return self._ok_response(["삼성전자"])

        with (
            patch.object(KISAPIClient, "_get_headers", return_value={"x": "y"}),
            patch("services.stock_service._http.get", side_effect=fake_get),
        ):
            KISAPIClient.get_volume_rank("J", blng_cls_code="0")
            KISAPIClient.get_volume_rank("J", blng_cls_code="3")

        assert sorted(calls) == ["0", "3"], f"캐시 키가 뭉쳤다: {calls}"

    def test_failure_falls_back_to_last_good(self):
        """빈 화면보다 조금 지난 순위가 낫다"""
        from services.stock_service import _rank_cache

        with (
            patch.object(KISAPIClient, "_get_headers", return_value={"x": "y"}),
            patch(
                "services.stock_service._http.get",
                return_value=self._ok_response(["삼성전자", "카카오"]),
            ),
        ):
            good = KISAPIClient.get_volume_rank("J")
        assert good

        # 신선한 캐시만 비우고(=TTL 만료 흉내) 조회를 실패시킨다
        _rank_cache._fresh.clear()
        with (
            patch.object(KISAPIClient, "_get_headers", return_value={"x": "y"}),
            patch("services.stock_service._http.get", side_effect=Timeout),
        ):
            stale = KISAPIClient.get_volume_rank("J")

        assert stale == good, "실패했다고 빈 목록을 돌려줬다"

    def test_no_last_good_returns_empty(self):
        """한 번도 성공한 적이 없으면 빈 목록이 맞다"""
        with (
            patch.object(KISAPIClient, "_get_headers", return_value={"x": "y"}),
            patch("services.stock_service._http.get", side_effect=Timeout),
        ):
            assert KISAPIClient.get_volume_rank("J") == []

    def test_http_error_also_falls_back(self):
        """타임아웃만 폴백하고 HTTP 에러는 빈 화면이면 반쪽짜리다"""
        from services.stock_service import _rank_cache

        class Err:
            status_code = 500
            text = "boom"

            @staticmethod
            def json():
                return {}

        with (
            patch.object(KISAPIClient, "_get_headers", return_value={"x": "y"}),
            patch(
                "services.stock_service._http.get",
                return_value=self._ok_response(["삼성전자"]),
            ),
        ):
            good = KISAPIClient.get_volume_rank("J")
        assert good

        _rank_cache._fresh.clear()
        with (
            patch.object(KISAPIClient, "_get_headers", return_value={"x": "y"}),
            patch("services.stock_service._http.get", return_value=Err()),
        ):
            assert KISAPIClient.get_volume_rank("J") == good


class TestBackgroundRefresh:
    """순위를 요청 경로 밖에서 미리 받아둔다"""

    def setup_method(self):
        from services.stock_service import _rank_cache

        _rank_cache.clear()

    def _ok_response(self):
        class R:
            status_code = 200

            @staticmethod
            def json():
                return {
                    "rt_cd": "0",
                    "output": [
                        {
                            "mksc_shrn_iscd": "005930",
                            "hts_kor_isnm": "삼성전자",
                            "stck_prpr": "1000",
                            "prdy_ctrt": "1.5",
                            "acml_vol": "100",
                            "acml_tr_pbmn": "1000",
                        }
                    ],
                }

        return R()

    def test_refresh_uses_its_own_generous_timeout(self):
        """배경 갱신에는 카카오 SLA가 없다. 요청 상한에 묶이면 할 이유가 없다"""
        seen = []

        def fake_get(url, headers=None, params=None, timeout=None):
            seen.append(timeout)
            return self._ok_response()

        with (
            patch.object(KISAPIClient, "_get_headers", return_value={"x": "y"}),
            patch("services.stock_service._http.get", side_effect=fake_get),
        ):
            StockService.refresh_rankings()

        assert seen, "배경 갱신이 KIS를 부르지 않았다"
        assert {sum(t) for t in seen} == {KISConfig.REFRESH_TIMEOUT}, (
            f"적용된 상한: {seen}"
        )
        assert KISConfig.REFRESH_TIMEOUT > KISConfig.RANK_TIMEOUT, (
            "요청 경로와 같은 상한이면 배경으로 뺀 의미가 없다"
        )

    def test_refresh_fills_cache_so_requests_make_no_call(self):
        """갱신 뒤 유저 요청은 메모리만 읽어야 한다"""
        with (
            patch.object(KISAPIClient, "_get_headers", return_value={"x": "y"}),
            patch(
                "services.stock_service._http.get",
                return_value=self._ok_response(),
            ),
        ):
            assert StockService.refresh_rankings() == len(StockService._WARM_RANK_KEYS)

        with patch(
            "services.stock_service._http.get",
            side_effect=AssertionError("요청 경로에서 KIS 호출됨"),
        ):
            for market, blng in StockService._WARM_RANK_KEYS:
                assert KISAPIClient.get_volume_rank(market, blng_cls_code=blng)

    def test_refresh_swallows_failures(self):
        """갱신이 예외를 던지면 배경 루프가 죽고 영영 낡은 값만 남는다"""
        with patch.object(
            KISAPIClient, "get_volume_rank", side_effect=RuntimeError("boom")
        ):
            assert StockService.refresh_rankings() == 0


class TestHttpTimeoutIsWallClock:
    """상한이 벽시계 시간을 뜻하지 않으면 예산 계산도 로그도 거짓말이 된다"""

    def test_sum_never_exceeds_the_cap(self):
        """합이 상한을 넘으면 예산 계산이 통째로 거짓말이 된다"""
        from services.stock_service import _http_timeout

        for total in (1.5, 3.0, 8.0, 20.0):
            connect, read = _http_timeout(total)
            assert connect + read <= total, (
                f"상한 {total}초인데 연결 {connect} + 응답 {read} = {connect + read}초"
            )

    def test_connect_share_grows_with_the_cap(self):
        """연결 몫이 고정 2초라 상한 20초짜리가 2.2초에 죽었다"""
        from services.stock_service import _http_timeout

        small_connect, _ = _http_timeout(KISConfig.RANK_TIMEOUT)
        big_connect, _ = _http_timeout(KISConfig.REFRESH_TIMEOUT)
        assert big_connect > small_connect, (
            "넉넉한 배경 호출인데 연결 몫이 요청 경로와 같다"
        )
        # 상한이 넉넉하면 설정값이 그대로 전선까지 가야 한다.
        # 여기가 하드코딩되면 20초짜리 호출이 또 2.2초에 죽는다.
        assert big_connect == KISConfig.CONNECT_TIMEOUT, (
            f"연결 몫 {big_connect}초 - 설정({KISConfig.CONNECT_TIMEOUT}초)이 안 쓰인다"
        )

    def test_connect_cap_clears_the_observed_failure(self):
        """실측 2.2초에 연결이 죽었다. 설정이 그보다 낮으면 같은 일이 반복된다"""
        assert KISConfig.CONNECT_TIMEOUT > 2.2

    def test_rank_call_passes_a_tuple(self):
        """스칼라로 넘기면 8초 상한이 최악 16초가 된다"""
        seen = {}

        def fake_get(url, headers=None, params=None, timeout=None):
            seen["timeout"] = timeout
            raise Timeout()

        with (
            patch.object(KISAPIClient, "_get_headers", return_value={"x": "y"}),
            patch("services.stock_service._http.get", side_effect=fake_get),
        ):
            KISAPIClient.get_volume_rank("J")

        assert isinstance(seen["timeout"], tuple), f"스칼라다: {seen['timeout']}"
        assert sum(seen["timeout"]) <= KISConfig.RANK_TIMEOUT


class TestRequestPathDefersToBackground:
    """순위는 배경 루프의 소유다. 요청 경로가 직접 부르면 예산만 태운다"""

    def setup_method(self):
        from services.stock_service import _rank_cache, _rank_circuit_breaker

        _rank_cache.clear()
        _rank_circuit_breaker.reset()

    teardown_method = setup_method

    def test_no_kis_call_during_a_kakao_request(self):
        """KIS 순위는 실측 17초다. 3초 상한에서 부르면 결과는 언제나 폴백이다"""
        from utils import budget

        with (
            patch.object(KISAPIClient, "_get_headers", return_value={"x": "y"}),
            patch(
                "services.stock_service._http.get",
                side_effect=AssertionError("요청 경로에서 KIS 호출됨"),
            ),
        ):
            with budget.request_budget(3.5):
                assert KISAPIClient.get_volume_rank("J") == []

    def test_stale_is_still_served_during_a_request(self):
        """부르지 않는 것과 안 보여주는 것은 다르다"""
        from services.stock_service import _rank_cache
        from utils import budget

        _rank_cache.put("volume:J:0", [{"code": "005930", "name": "삼성전자"}])
        _rank_cache._fresh.clear()

        with budget.request_budget(3.5):
            got = KISAPIClient.get_volume_rank("J")
        assert got and got[0]["name"] == "삼성전자"

    def test_background_still_calls_kis(self):
        """deadline이 없는 배경 경로까지 막으면 캐시를 채울 사람이 없다"""
        calls = []

        def fake_get(url, headers=None, params=None, timeout=None):
            calls.append(url)
            raise Timeout()

        with (
            patch.object(KISAPIClient, "_get_headers", return_value={"x": "y"}),
            patch("services.stock_service._http.get", side_effect=fake_get),
        ):
            KISAPIClient.get_volume_rank("J", timeout_cap=KISConfig.REFRESH_TIMEOUT)

        assert calls, "배경 갱신까지 막혔다"


class TestConnectionReuse:
    """호출마다 TLS 핸드셰이크를 새로 하면 연결 단계에서만 죽는다"""

    def test_calls_go_through_a_shared_session(self):
        from services import stock_service

        assert isinstance(stock_service._http, requests.Session), (
            "requests.get()는 호출마다 새 Session을 만든다 = 매번 핸드셰이크"
        )

    def test_session_does_not_retry_behind_our_back(self):
        """urllib3가 몰래 재시도하면 우리가 계산한 상한이 배가 된다"""
        from services import stock_service

        adapter = stock_service._http.get_adapter("https://openapi.koreainvestment.com")
        assert adapter.max_retries.total == 0, (
            f"재시도가 {adapter.max_retries.total}회 - 상한이 그만큼 늘어난다"
        )

    def test_pool_covers_concurrent_calls(self):
        """동시 호출 상한보다 풀이 작으면 남는 호출이 새로 연결한다"""
        from services import stock_service

        adapter = stock_service._http.get_adapter("https://openapi.koreainvestment.com")
        assert adapter._pool_maxsize >= KISConfig.MAX_CONCURRENT_CALLS


class TestTimeoutLogNamesThePhase:
    """어느 단계가 죽었는지 모르면 대기 시간으로 역산해야 한다"""

    def setup_method(self):
        from services.stock_service import _rank_cache, _rank_circuit_breaker

        _rank_cache.clear()
        _rank_circuit_breaker.reset()

    teardown_method = setup_method

    def _log_for(self, exc, caplog):
        with (
            patch.object(KISAPIClient, "_get_headers", return_value={"x": "y"}),
            patch("services.stock_service._http.get", side_effect=exc),
            caplog.at_level(logging.WARNING, logger=SERVICE_LOGGER),
        ):
            KISAPIClient.get_volume_rank("J")
        msgs = [r.message for r in caplog.records if "순위 조회 타임아웃" in r.message]
        assert msgs, "타임아웃 로그가 없다"
        return msgs[0]

    def test_connect_timeout_says_connect_and_its_own_cap(self, caplog):
        from services.stock_service import _http_timeout

        msg = self._log_for(ConnectTimeout, caplog)
        connect, _ = _http_timeout(KISConfig.RANK_TIMEOUT)
        assert "연결" in msg, f"단계가 없다: {msg}"
        assert f"상한 {connect:.2f}초" in msg, (
            f"전체 상한을 찍으면 실제 적용된 연결 상한을 알 수 없다: {msg}"
        )

    def test_read_timeout_says_read_and_its_own_cap(self, caplog):
        from services.stock_service import _http_timeout

        msg = self._log_for(ReadTimeout, caplog)
        _, read = _http_timeout(KISConfig.RANK_TIMEOUT)
        assert "응답" in msg, f"단계가 없다: {msg}"
        assert f"상한 {read:.2f}초" in msg


class TestRankCircuitIsSeparate:
    """느린 순위 하나가 시세·매수·매도를 막으면 안 된다"""

    def setup_method(self):
        from services.stock_service import _circuit_breaker, _rank_circuit_breaker
        from services.stock_service import _rank_cache

        _circuit_breaker.reset()
        _rank_circuit_breaker.reset()
        _rank_cache.clear()

    teardown_method = setup_method

    def test_rank_failures_do_not_open_price_circuit(self):
        """순위가 8초씩 걸린다고 종목별 현재가까지 막을 이유가 없다"""
        from services.stock_service import _circuit_breaker, _rank_circuit_breaker
        from utils.resilience import CircuitState

        with (
            patch.object(KISAPIClient, "_get_headers", return_value={"x": "y"}),
            patch("services.stock_service._http.get", side_effect=Timeout),
        ):
            for _ in range(KISConfig.CIRCUIT_FAILURE_THRESHOLD + 2):
                KISAPIClient.get_volume_rank("J")

        assert _rank_circuit_breaker.state == CircuitState.OPEN, (
            "순위 서킷은 열려야 한다 - 계속 두드릴 이유가 없다"
        )
        assert _circuit_breaker.state == CircuitState.CLOSED, (
            "순위가 느리다고 시세 서킷이 열리면 매수·매도가 통째로 막힌다"
        )

    def test_price_query_works_while_rank_circuit_is_open(self):
        """순위 서킷이 열린 상태에서도 시세는 나가야 한다"""
        from services.stock_service import _rank_circuit_breaker
        from utils.resilience import CircuitState

        with (
            patch.object(KISAPIClient, "_get_headers", return_value={"x": "y"}),
            patch("services.stock_service._http.get", side_effect=Timeout),
        ):
            for _ in range(KISConfig.CIRCUIT_FAILURE_THRESHOLD + 2):
                KISAPIClient.get_volume_rank("J")
        assert _rank_circuit_breaker.state == CircuitState.OPEN

        called = []

        class PriceResp:
            status_code = 200

            @staticmethod
            def json():
                return {
                    "rt_cd": "0",
                    "output": {
                        "stck_prpr": "70000",
                        "prdy_vrss": "1000",
                        "prdy_ctrt": "1.45",
                        "acml_vol": "1000",
                        "hts_kor_isnm": "삼성전자",
                    },
                }

        def fake_get(url, headers=None, params=None, timeout=None):
            called.append(url)
            return PriceResp()

        with (
            patch.object(KISAPIClient, "_get_headers", return_value={"x": "y"}),
            patch("services.stock_service._http.get", side_effect=fake_get),
        ):
            price = KISAPIClient.get_stock_price("005930")

        assert called, "순위 서킷이 시세 호출까지 막았다"
        assert price and price["price"] == 70000


class TestRankRefreshLoop:
    """배경 루프는 어떤 이유로도 멈추지 않는다"""

    class _Stop(BaseException):
        """루프를 한 바퀴만 돌리기 위한 탈출 신호 (except Exception에 안 걸린다)"""

    def _run_one_tick(self, market_open, refresher):
        import main

        async def stop_sleep(_):
            raise self._Stop()

        with (
            patch.object(main, "is_market_open", return_value=market_open),
            patch.object(main.StockService, "refresh_rankings", refresher),
            patch("main.asyncio.sleep", stop_sleep),
        ):
            with pytest.raises(self._Stop):
                asyncio.run(main._rank_refresh_loop())

    def test_skips_when_market_closed(self):
        """장이 닫히면 순위가 변하지 않는다. 부를 이유가 없다"""
        refresher = MagicMock(return_value=2)
        self._run_one_tick(market_open=False, refresher=refresher)
        refresher.assert_not_called()

    def test_refreshes_when_market_open(self):
        refresher = MagicMock(return_value=2)
        self._run_one_tick(market_open=True, refresher=refresher)
        refresher.assert_called_once()

    def test_survives_refresh_exception(self):
        """한 번 실패했다고 루프가 끝나면 그 뒤로 갱신이 영영 없다"""
        refresher = MagicMock(side_effect=RuntimeError("boom"))
        # _Stop은 sleep에서 나온다 = 예외를 먹고 다음 주기로 넘어갔다는 뜻
        self._run_one_tick(market_open=True, refresher=refresher)
        refresher.assert_called_once()


class TestNoHiddenKisCallInButtons:
    """버튼을 만들려고 KIS를 부르면 안 된다"""

    def test_popular_button_never_calls_kis(self):
        """순위가 실패한 화면에서 버튼 때문에 또 부르면 예산이 남지 않는다"""
        from handlers.base_handler import BaseHandlerMixin

        BaseHandlerMixin._popular_stock_cache.clear()

        with patch.object(
            KISAPIClient, "get_volume_rank", side_effect=AssertionError("KIS 호출됨")
        ):
            handler = BaseHandlerMixin()
            btn = handler._popular_stock_btn()

        assert btn["messageText"] == "/인기"

    def test_remembered_name_is_used(self):
        from handlers.base_handler import BaseHandlerMixin

        BaseHandlerMixin.remember_popular_stock("삼성전자")
        btn = BaseHandlerMixin()._popular_stock_btn()
        assert "삼성전자" in btn["messageText"]
        BaseHandlerMixin._popular_stock_cache.clear()
