"""
급등/급락 순위 필터링 테스트
- 레버리지/인버스 등 지수 배율 상품이 급등/급락 순위에서 제외되는지 검증
- get_volume_rank 결과를 등락률로 재정렬하는 로직 검증
"""
from unittest.mock import patch

from config import KISConfig
from services.stock_service import KISAPIClient


# 거래량 순위 모킹 데이터 (레버리지/인버스 + 일반 종목 혼합)
SAMPLE_VOLUME_RANK = [
    {"code": "122630", "name": "KODEX 레버리지", "price": 20000, "change": 5.5, "volume": 1000},
    {"code": "252670", "name": "KODEX 200선물인버스2X", "price": 3000, "change": -6.0, "volume": 900},
    {"code": "005930", "name": "삼성전자", "price": 70000, "change": 3.2, "volume": 800},
    {"code": "000660", "name": "SK하이닉스", "price": 150000, "change": -4.1, "volume": 700},
    {"code": "035720", "name": "카카오", "price": 50000, "change": 1.0, "volume": 600},
    {"code": "373220", "name": "LG에너지솔루션", "price": 400000, "change": -2.0, "volume": 500},
]


def test_excluded_from_ranking_detects_leverage_inverse():
    """레버리지/인버스 종목명은 제외 대상으로 판단한다"""
    assert KISAPIClient._is_excluded_from_ranking("KODEX 레버리지") is True
    assert KISAPIClient._is_excluded_from_ranking("KODEX 200선물인버스2X") is True
    assert KISAPIClient._is_excluded_from_ranking("KODEX 코스닥150레버리지") is True
    # 일반 종목은 제외하지 않는다
    assert KISAPIClient._is_excluded_from_ranking("삼성전자") is False
    assert KISAPIClient._is_excluded_from_ranking("SK하이닉스") is False
    assert KISAPIClient._is_excluded_from_ranking("") is False


def test_gainers_exclude_leverage():
    """급등주(sort=1)에 레버리지/인버스가 포함되지 않는다"""
    with patch.object(KISAPIClient, "get_volume_rank", return_value=list(SAMPLE_VOLUME_RANK)):
        result = KISAPIClient.get_fluctuation_rank(sort="1")

    names = [s["name"] for s in result]
    assert "KODEX 레버리지" not in names
    assert "KODEX 200선물인버스2X" not in names
    # 일반 종목 중 등락률 최상위인 삼성전자(+3.2)가 1위
    assert result[0]["name"] == "삼성전자"
    # 상승률 내림차순 정렬 확인
    changes = [s["change"] for s in result]
    assert changes == sorted(changes, reverse=True)


def test_losers_exclude_leverage():
    """급락주(sort=2)에 레버리지/인버스가 포함되지 않는다"""
    with patch.object(KISAPIClient, "get_volume_rank", return_value=list(SAMPLE_VOLUME_RANK)):
        result = KISAPIClient.get_fluctuation_rank(sort="2")

    names = [s["name"] for s in result]
    assert "KODEX 200선물인버스2X" not in names
    assert "KODEX 레버리지" not in names
    # 일반 종목 중 등락률 최하위인 SK하이닉스(-4.1)가 1위
    assert result[0]["name"] == "SK하이닉스"
    # 하락률 오름차순 정렬 확인
    changes = [s["change"] for s in result]
    assert changes == sorted(changes)


def test_fluctuation_rank_empty_when_no_data():
    """거래량 데이터가 없으면 빈 리스트를 반환한다"""
    with patch.object(KISAPIClient, "get_volume_rank", return_value=[]):
        assert KISAPIClient.get_fluctuation_rank(sort="1") == []


def test_all_excluded_returns_empty():
    """후보가 전부 제외 대상이면 빈 리스트를 반환한다"""
    only_leverage = [
        {"code": "122630", "name": "KODEX 레버리지", "price": 20000, "change": 5.5, "volume": 1000},
        {"code": "252670", "name": "KODEX 인버스", "price": 3000, "change": -6.0, "volume": 900},
    ]
    with patch.object(KISAPIClient, "get_volume_rank", return_value=only_leverage):
        assert KISAPIClient.get_fluctuation_rank(sort="1") == []


def test_exclude_keywords_configurable():
    """제외 키워드는 config(KISConfig.RANKING_EXCLUDE_KEYWORDS)에서 관리된다"""
    assert "레버리지" in KISConfig.RANKING_EXCLUDE_KEYWORDS
    assert "인버스" in KISConfig.RANKING_EXCLUDE_KEYWORDS
