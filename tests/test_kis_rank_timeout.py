"""순위 조회 타임아웃 진단 검증"""

import time
from unittest.mock import patch
from requests.exceptions import Timeout

from services.stock_service import KISAPIClient
from settings import KISConfig


def test_rank_uses_its_own_timeout(caplog):
    """순위 조회는 단일 시세보다 넉넉한 상한을 쓴다"""
    seen = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        seen["timeout"] = timeout
        raise Timeout()

    with (
        patch.object(KISAPIClient, "_get_headers", return_value={"x": "y"}),
        patch("services.stock_service.requests.get", side_effect=fake_get),
    ):
        result = KISAPIClient.get_volume_rank("J")

    assert result == []
    assert seen["timeout"] == KISConfig.RANK_TIMEOUT
    assert seen["timeout"] > KISConfig.API_TIMEOUT, "시세 상한과 같으면 의미가 없다"


def test_timeout_log_shows_elapsed_and_cap(caplog):
    """'타임아웃'만 찍으면 상류가 느린 건지 우리가 좁게 준 건지 모른다"""

    def slow_then_timeout(url, headers=None, params=None, timeout=None):
        time.sleep(0.05)
        raise Timeout()

    with (
        patch.object(KISAPIClient, "_get_headers", return_value={"x": "y"}),
        patch("services.stock_service.requests.get", side_effect=slow_then_timeout),
        caplog.at_level("WARNING"),
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
            patch("services.stock_service.requests.get", side_effect=fake_get),
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
            patch("services.stock_service.requests.get", side_effect=fake_get),
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
                "services.stock_service.requests.get",
                return_value=self._ok_response(["삼성전자", "카카오"]),
            ),
        ):
            good = KISAPIClient.get_volume_rank("J")
        assert good

        # 신선한 캐시만 비우고(=TTL 만료 흉내) 조회를 실패시킨다
        _rank_cache._fresh.clear()
        with (
            patch.object(KISAPIClient, "_get_headers", return_value={"x": "y"}),
            patch("services.stock_service.requests.get", side_effect=Timeout),
        ):
            stale = KISAPIClient.get_volume_rank("J")

        assert stale == good, "실패했다고 빈 목록을 돌려줬다"

    def test_no_last_good_returns_empty(self):
        """한 번도 성공한 적이 없으면 빈 목록이 맞다"""
        with (
            patch.object(KISAPIClient, "_get_headers", return_value={"x": "y"}),
            patch("services.stock_service.requests.get", side_effect=Timeout),
        ):
            assert KISAPIClient.get_volume_rank("J") == []


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
