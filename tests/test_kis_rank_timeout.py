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
