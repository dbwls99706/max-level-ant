"""
한국 증시 영업일/운영시간 계산
- 공휴일(휴장일) 목록
- 장 상태 판정 (휴장 / 동시호가 / 정규장 / 시간외)

모든 시각 계산은 서버 타임존과 무관하게 UTC → KST 변환으로 수행한다.
"""

import logging
from datetime import date, datetime, timezone
from typing import Optional

import pytz

logger = logging.getLogger(__name__)

# 한국 시간대
KST = pytz.timezone("Asia/Seoul")


# ===========================================
# 장 상태
# ===========================================
class MarketStatus:
    """장 상태 코드"""

    CLOSED = "CLOSED"  # 완전 휴장 (주말, 공휴일, 18:00~08:30)
    PRE_MARKET = "PRE_MARKET"  # 동시호가 (08:30~09:00)
    REGULAR = "REGULAR"  # 정규장 (09:00~15:30)
    AFTER_HOURS = "AFTER_HOURS"  # 시간외 거래 (15:40~18:00)


# 장 운영시간 경계 (KST 기준, 자정으로부터의 분)
_PRE_MARKET_OPEN = 8 * 60 + 30  # 08:30
_REGULAR_OPEN = 9 * 60  # 09:00
_REGULAR_CLOSE = 15 * 60 + 30  # 15:30
_AFTER_HOURS_OPEN = 15 * 60 + 40  # 15:40
_AFTER_HOURS_CLOSE = 18 * 60  # 18:00

# 거래 가능한 장 상태 (매수/매도 허용)
TRADING_STATUSES = frozenset(
    {MarketStatus.PRE_MARKET, MarketStatus.REGULAR, MarketStatus.AFTER_HOURS}
)


# ===========================================
# 공휴일 목록 (2024-2026)
# ===========================================
HOLIDAYS = {
    # 2024년
    date(2024, 1, 1),  # 신정
    date(2024, 2, 9),  # 설날 연휴
    date(2024, 2, 10),  # 설날
    date(2024, 2, 11),  # 설날 연휴
    date(2024, 2, 12),  # 대체공휴일
    date(2024, 3, 1),  # 삼일절
    date(2024, 4, 10),  # 국회의원선거일
    date(2024, 5, 5),  # 어린이날
    date(2024, 5, 6),  # 대체공휴일
    date(2024, 5, 15),  # 부처님오신날
    date(2024, 6, 6),  # 현충일
    date(2024, 8, 15),  # 광복절
    date(2024, 9, 16),  # 추석 연휴
    date(2024, 9, 17),  # 추석
    date(2024, 9, 18),  # 추석 연휴
    date(2024, 10, 3),  # 개천절
    date(2024, 10, 9),  # 한글날
    date(2024, 12, 25),  # 성탄절
    date(2024, 12, 31),  # 연말 휴장
    # 2025년
    date(2025, 1, 1),  # 신정
    date(2025, 1, 28),  # 설날 연휴
    date(2025, 1, 29),  # 설날
    date(2025, 1, 30),  # 설날 연휴
    date(2025, 3, 1),  # 삼일절
    date(2025, 3, 3),  # 대체공휴일
    date(2025, 5, 5),  # 어린이날
    date(2025, 5, 6),  # 부처님오신날
    date(2025, 6, 6),  # 현충일
    date(2025, 8, 15),  # 광복절
    date(2025, 10, 3),  # 개천절
    date(2025, 10, 5),  # 추석 연휴
    date(2025, 10, 6),  # 추석
    date(2025, 10, 7),  # 추석 연휴
    date(2025, 10, 8),  # 대체공휴일
    date(2025, 10, 9),  # 한글날
    date(2025, 12, 25),  # 성탄절
    # 2026년
    date(2026, 1, 1),  # 신정
    date(2026, 2, 16),  # 설날 연휴
    date(2026, 2, 17),  # 설날
    date(2026, 2, 18),  # 설날 연휴
    date(2026, 3, 1),  # 삼일절
    date(2026, 3, 2),  # 대체공휴일
    date(2026, 5, 5),  # 어린이날
    date(2026, 5, 24),  # 부처님오신날
    date(2026, 5, 25),  # 대체공휴일
    date(2026, 6, 6),  # 현충일
    date(2026, 8, 15),  # 광복절
    date(2026, 8, 17),  # 대체공휴일
    date(2026, 9, 24),  # 추석 연휴
    date(2026, 9, 25),  # 추석
    date(2026, 9, 26),  # 추석 연휴
    date(2026, 10, 3),  # 개천절
    date(2026, 10, 5),  # 대체공휴일
    date(2026, 10, 9),  # 한글날
    date(2026, 12, 25),  # 성탄절
}

# 공휴일 데이터가 커버하는 연도 범위 (경고 판정용)
HOLIDAY_YEARS = frozenset(d.year for d in HOLIDAYS)


def now_kst() -> datetime:
    """현재 KST 시각 (서버 타임존 무관)"""
    return datetime.now(timezone.utc).astimezone(KST)


def is_holiday(check_date: Optional[date] = None) -> bool:
    """공휴일 여부 확인"""
    if check_date is None:
        check_date = now_kst().date()
    return check_date in HOLIDAYS


def has_holiday_data(year: Optional[int] = None) -> bool:
    """해당 연도의 공휴일 데이터가 등록돼 있는지"""
    if year is None:
        year = now_kst().year
    return year in HOLIDAY_YEARS


def get_market_status() -> str:
    """
    현재 장 상태 반환 (MarketStatus 값)
    - CLOSED: 완전 휴장 (주말, 공휴일, 18:00~08:30)
    - PRE_MARKET: 동시호가 (08:30~09:00)
    - REGULAR: 정규장 (09:00~15:30)
    - AFTER_HOURS: 시간외 거래 (15:40~18:00)
    """
    now = now_kst()

    # 주말 체크
    if now.weekday() >= 5:
        return MarketStatus.CLOSED

    # 공휴일 체크
    if is_holiday(now.date()):
        return MarketStatus.CLOSED

    minutes = now.hour * 60 + now.minute

    if minutes < _PRE_MARKET_OPEN:
        return MarketStatus.CLOSED
    if minutes < _REGULAR_OPEN:
        return MarketStatus.PRE_MARKET
    if minutes < _REGULAR_CLOSE:
        return MarketStatus.REGULAR
    if minutes < _AFTER_HOURS_OPEN:
        return MarketStatus.CLOSED  # 15:30~15:40 휴식
    if minutes < _AFTER_HOURS_CLOSE:
        return MarketStatus.AFTER_HOURS
    return MarketStatus.CLOSED


def is_market_closed() -> bool:
    """장이 완전히 닫혀있는지 (거래 불가)"""
    return get_market_status() == MarketStatus.CLOSED


def is_market_open() -> bool:
    """정규장이 열려있는지"""
    return get_market_status() == MarketStatus.REGULAR


def is_trading_available() -> bool:
    """거래 가능 시간인지 (동시호가 + 정규장 + 시간외)"""
    return get_market_status() in TRADING_STATUSES


def get_market_status_message() -> str:
    """현재 장 상태 메시지"""
    status = get_market_status()

    if status == MarketStatus.PRE_MARKET:
        return "🟡 동시호가 (08:30~09:00)"
    if status == MarketStatus.REGULAR:
        return "🟢 정규장 (09:00~15:30)"
    if status == MarketStatus.AFTER_HOURS:
        return "🟠 시간외 거래 (15:40~18:00)"

    now = now_kst()
    if now.weekday() >= 5:
        return "🔴 휴장 (주말)"
    if is_holiday(now.date()):
        return "🔴 휴장 (공휴일)"
    if now.hour * 60 + now.minute < _PRE_MARKET_OPEN:
        return "🔴 휴장 (장 시작 전)"
    return "🔴 휴장 (장 마감)"


# 공휴일 목록 연도 커버리지 확인
if not has_holiday_data():
    logger.warning(
        f"공휴일 목록에 {now_kst().year}년 데이터가 없습니다. "
        f"공휴일 체크가 정상 작동하지 않을 수 있습니다. "
        f"market_calendar.py의 HOLIDAYS를 업데이트해주세요."
    )
