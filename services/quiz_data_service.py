"""
역사 퀴즈 데이터 서비스
- pykrx를 사용하여 실제 한국 주식 과거 데이터 기반 퀴즈 생성
- 캐시로 API 호출 최소화
- 주식 추천 절대 금지, 비하 표현 금지
"""
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from cachetools import TTLCache

from config import GameProbability, KST
from utils import get_service_logger

logger = get_service_logger()

# 퀴즈 데이터 캐시 (6시간 TTL, 최대 1개 엔트리)
_quiz_cache: TTLCache = TTLCache(maxsize=1, ttl=6 * 3600)

# pykrx 사용 가능 여부
_pykrx_available = False
try:
    from pykrx import stock as pykrx_stock
    _pykrx_available = True
except ImportError:
    logger.warning("pykrx 미설치 — 하드코딩된 퀴즈 데이터 사용")

# 퀴즈 대상 종목 (티커, 종목명)
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

# 변동률에 따른 중립적 설명 템플릿 (추천/비하 없이 사실만 기술)
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


def _generate_period_quiz(ticker: str, stock_name: str) -> Optional[Dict]:
    """
    pykrx를 사용하여 특정 종목의 랜덤 기간 퀴즈 생성
    - 1~3년 전 시점에서 3~12개월 기간의 주가 변동을 퀴즈로 출제
    """
    if not _pykrx_available:
        return None

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

        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")

        # pykrx로 월봉 데이터 조회 (호출 최소화)
        df = pykrx_stock.get_market_ohlcv_by_date(start_str, end_str, ticker, "m")

        if df is None or len(df) < 2:
            return None

        # 시작가와 종가 비교
        first_close = df.iloc[0]["종가"]
        last_close = df.iloc[-1]["종가"]

        if first_close == 0:
            return None

        change_pct = ((last_close - first_close) / first_close) * 100

        # 변동률이 너무 작으면 (±3% 미만) 스킵 — 퀴즈로 재미없음
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
        logger.debug(f"pykrx 퀴즈 생성 실패 ({stock_name}): {e}")
        return None


def _build_quiz_pool() -> List[Dict]:
    """
    퀴즈 풀 생성: pykrx로 실제 데이터 기반 퀴즈 + 하드코딩 폴백
    - 목표: 최소 20개 퀴즈
    - pykrx 실패 시 하드코딩 데이터로 폴백
    """
    quizzes = []

    if _pykrx_available:
        # 각 종목에서 1~2개씩 퀴즈 생성 시도
        shuffled = list(QUIZ_STOCKS)
        random.shuffle(shuffled)

        for ticker, name in shuffled:
            attempts = random.randint(1, 2)
            for _ in range(attempts):
                quiz = _generate_period_quiz(ticker, name)
                if quiz:
                    quizzes.append(quiz)
                if len(quizzes) >= 30:
                    break
            if len(quizzes) >= 30:
                break

    # pykrx 결과가 부족하면 하드코딩 데이터로 보충
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
