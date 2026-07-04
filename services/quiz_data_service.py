"""
역사 퀴즈 데이터 서비스
- 공공데이터포털(금융위원회_주식시세정보) API로 실제 과거 주가 데이터 기반 퀴즈 생성
- 캐시로 API 호출 최소화 (6시간 TTL)
- 주식 추천 절대 금지, 비하 표현 금지
"""

import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from cachetools import TTLCache
import requests

from config import PublicDataConfig, GameProbability, KST
from utils import get_service_logger

logger = get_service_logger()

# 퀴즈 데이터 캐시 (6시간 TTL, 최대 1개 엔트리)
_quiz_cache: TTLCache = TTLCache(maxsize=1, ttl=6 * 3600)

# 퀴즈 대상 종목 (단축코드, 종목명)
QUIZ_STOCKS = [
    ("005930", "삼성전자"),
    ("000660", "SK하이닉스"),
    ("035420", "네이버"),
    ("035720", "카카오"),
    ("005380", "현대자동차"),
    ("068270", "셀트리온"),
    ("373220", "LG에너지솔루션"),
    ("051910", "LG화학"),
    ("005490", "POSCO홀딩스"),
    ("006400", "삼성SDI"),
    ("000270", "기아"),
    ("207940", "삼성바이오로직스"),
    ("012450", "한화에어로스페이스"),
    ("259960", "크래프톤"),
    ("055550", "신한지주"),
    ("105560", "KB금융"),
    ("003670", "포스코퓨처엠"),
    ("028260", "삼성물산"),
    ("066570", "LG전자"),
    ("096770", "SK이노베이션"),
]

# 중립적 설명 템플릿 (추천/비하 없이 사실만 기술)
_RISE_DESCRIPTIONS = [
    "해당 기간 동안 주가가 상승세를 보였습니다",
    "시장에서 긍정적인 흐름이 이어졌습니다",
    "투자자들의 관심이 높아지며 주가가 올랐습니다",
    "업종 전반의 호조 속에 상승했습니다",
    "실적 기대감 등으로 주가가 올랐습니다",
]

_FALL_DESCRIPTIONS = [
    "해당 기간 동안 주가가 하락세를 보였습니다",
    "시장 전반의 조정 흐름 속에 하락했습니다",
    "투자 심리 위축으로 주가가 내렸습니다",
    "업종 전반의 약세 속에 하락했습니다",
    "외부 환경 변화로 주가가 조정을 받았습니다",
]


def _fetch_stock_prices(
    ticker: str, begin_dt: str, end_dt: str
) -> Optional[List[Dict]]:
    """
    공공데이터포털 API로 종목의 기간별 종가 조회
    - begin_dt, end_dt: YYYYMMDD 형식
    - 반환: [{basDt, clpr}, ...] 리스트 (날짜순)
    """
    if not PublicDataConfig.SERVICE_KEY:
        return None

    try:
        url = f"{PublicDataConfig.BASE_URL}/getStockPriceInfo"
        params = {
            "serviceKey": PublicDataConfig.SERVICE_KEY,
            "numOfRows": 100,
            "pageNo": 1,
            "resultType": "json",
            "likeSrtnCd": ticker,
            "beginBasDt": begin_dt,
            "endBasDt": end_dt,
        }

        resp = requests.get(url, params=params, timeout=PublicDataConfig.API_TIMEOUT)
        resp.raise_for_status()

        data = resp.json()
        body = data.get("response", {}).get("body", {})
        items = body.get("items", {}).get("item", [])

        if not items:
            return None

        # 날짜 오름차순 정렬
        items.sort(key=lambda x: x.get("basDt", ""))
        return items

    except Exception as e:
        logger.debug(f"공공데이터 API 호출 실패 ({ticker}): {e}")
        return None


def _generate_period_quiz(ticker: str, stock_name: str) -> Optional[Dict]:
    """
    공공데이터포털 API로 특정 종목의 랜덤 기간 퀴즈 생성
    - 1~7년 전 시점에서 3~12개월 기간의 주가 변동을 퀴즈로 출제
    """
    try:
        now = datetime.now(KST)

        # 랜덤 시작점: 1~7년 전
        years_ago = random.randint(1, 7)
        months_offset = random.randint(0, 11)
        start_date = now - timedelta(days=365 * years_ago + 30 * months_offset)

        # 랜덤 기간: 3~12개월
        period_months = random.randint(3, 12)
        end_date = start_date + timedelta(days=30 * period_months)

        # 미래 날짜 방지
        if end_date >= now - timedelta(days=30):
            end_date = now - timedelta(days=30)
            if (end_date - start_date).days < 60:
                return None

        # 시작일 근처 + 종료일 근처 종가만 필요 → 각각 짧은 구간 조회 (API 호출 절약)
        start_begin = start_date.strftime("%Y%m%d")
        start_end = (start_date + timedelta(days=14)).strftime("%Y%m%d")

        end_begin = (end_date - timedelta(days=14)).strftime("%Y%m%d")
        end_end = end_date.strftime("%Y%m%d")

        start_items = _fetch_stock_prices(ticker, start_begin, start_end)
        if not start_items:
            return None

        end_items = _fetch_stock_prices(ticker, end_begin, end_end)
        if not end_items:
            return None

        # 시작 종가 (기간의 첫 거래일)
        first_close = int(start_items[0].get("clpr", 0))
        # 종료 종가 (기간의 마지막 거래일)
        last_close = int(end_items[-1].get("clpr", 0))

        if first_close == 0:
            return None

        change_pct = ((last_close - first_close) / first_close) * 100

        # 변동률이 너무 작으면 (±3% 미만) 스킵
        if abs(change_pct) < 3:
            return None

        answer = "상승" if change_pct > 0 else "하락"
        abs_pct = abs(change_pct)

        # 기간 포맷
        start_display = start_date.strftime("%Y년 %m월")
        end_display = end_date.strftime("%Y년 %m월")

        # 중립적 설명 생성 (추천/비하 없이)
        if answer == "상승":
            desc = random.choice(_RISE_DESCRIPTIONS)
            desc += f" (약 {abs_pct:.0f}% 상승)"
        else:
            desc = random.choice(_FALL_DESCRIPTIONS)
            desc += f" (약 {abs_pct:.0f}% 하락)"

        return {
            "stock_name": stock_name,
            "period": f"{start_display} ~ {end_display}",
            "answer": answer,
            "description": desc,
        }

    except Exception as e:
        logger.debug(f"퀴즈 생성 실패 ({stock_name}): {e}")
        return None


def _build_quiz_pool() -> List[Dict]:
    """
    퀴즈 풀 생성: 공공데이터포털 API로 실제 데이터 기반 퀴즈 + 하드코딩 폴백
    - 목표: 최소 20개 퀴즈
    - API 실패 시 하드코딩 데이터로 폴백
    """
    quizzes = []

    if PublicDataConfig.SERVICE_KEY:
        # 각 종목에서 1~2개씩 퀴즈 생성 시도
        shuffled = list(QUIZ_STOCKS)
        random.shuffle(shuffled)

        for ticker, name in shuffled:
            quiz = _generate_period_quiz(ticker, name)
            if quiz:
                quizzes.append(quiz)
            if len(quizzes) >= 30:
                break

    # API 결과가 부족하면 하드코딩 데이터로 보충
    if len(quizzes) < 10:
        fallback = list(GameProbability.HISTORICAL_STOCK_DATA)
        random.shuffle(fallback)
        needed = max(0, 20 - len(quizzes))
        quizzes.extend(fallback[:needed])

    if not quizzes:
        quizzes = list(GameProbability.HISTORICAL_STOCK_DATA)

    return quizzes


def get_random_quiz() -> Dict:
    """
    랜덤 퀴즈 1개 반환 (캐시된 풀에서 선택)
    """
    cache_key = "quiz_pool"

    if cache_key not in _quiz_cache:
        logger.info("퀴즈 풀 생성 중...")
        pool = _build_quiz_pool()
        _quiz_cache[cache_key] = pool
        logger.info(f"퀴즈 풀 생성 완료: {len(pool)}개")

    pool = _quiz_cache[cache_key]
    return random.choice(pool)
