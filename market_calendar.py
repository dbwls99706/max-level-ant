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
# 휴장일 데이터
# ===========================================
# 증시 휴장일 = 한국 법정공휴일 + KRX 전용 휴장일
#
# ⚠️ 이 데이터는 손으로 관리한다. 공휴일법 개정·임시공휴일·선거일이 생기면
#    반드시 갱신해야 하며, COVERED_YEARS 밖의 날짜는 판정이 부정확하다.
#    (기동 시 has_holiday_data()가 현재 연도 커버 여부를 경고한다)
#
# 법정공휴일 (대체공휴일·임시공휴일·선거일 포함)
PUBLIC_HOLIDAYS = {
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
    date(2026, 5, 1),  # 노동절 (2026년부터 법정공휴일)
    date(2026, 5, 5),  # 어린이날
    date(2026, 5, 24),  # 부처님오신날
    date(2026, 5, 25),  # 대체공휴일
    date(2026, 6, 3),  # 제9회 전국동시지방선거일
    date(2026, 6, 6),  # 현충일
    date(2026, 7, 17),  # 제헌절 (공휴일 재지정)
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

# 공휴일 데이터가 커버하는 연도
COVERED_YEARS = frozenset(d.year for d in PUBLIC_HOLIDAYS)

# 근로자의 날(5/1)
# 2026년 5월 1일부터 법정공휴일로 편입됐다. 그 이전에는 법정공휴일이 아니지만
# KRX는 휴장했으므로 KRX 전용 휴장일로 분류한다.
# (결과적인 휴장 여부는 같지만, PUBLIC/KRX_ONLY의 의미를 정확히 유지한다)
LABOR_DAY_MONTH_DAY = (5, 1)
LABOR_DAY_PUBLIC_HOLIDAY_FROM = 2026


def _krx_only_labor_days() -> set:
    """법정공휴일이 되기 전(2026 이전)의 근로자의 날"""
    return {
        date(y, *LABOR_DAY_MONTH_DAY)
        for y in COVERED_YEARS
        if y < LABOR_DAY_PUBLIC_HOLIDAY_FROM
    }


def _year_end_closure(year: int) -> date:
    """
    연말 휴장일 - 그 해의 마지막 영업일.

    12/31부터 거꾸로 내려가며 주말·공휴일이 아닌 첫 날을 찾는다.
    (예: 2024·2025·2026년은 12/31이 평일이라 12/31이 휴장일)
    """
    day = date(year, 12, 31)
    while day.weekday() >= 5 or day in PUBLIC_HOLIDAYS:
        day = day.replace(day=day.day - 1)
    return day


def _year_end_closures() -> set:
    return {_year_end_closure(y) for y in COVERED_YEARS}


# KRX 전용 휴장일 (법정공휴일은 아니지만 증시는 쉬는 날)
KRX_ONLY_CLOSURES = _krx_only_labor_days() | _year_end_closures()

# 최종 휴장일 = 법정공휴일 + KRX 전용 휴장일
HOLIDAYS = PUBLIC_HOLIDAYS | KRX_ONLY_CLOSURES

# 하위 호환 (기존 이름)
HOLIDAY_YEARS = COVERED_YEARS


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
    return year in COVERED_YEARS


def is_trading_day(check_date: Optional[date] = None) -> bool:
    """
    해당 날짜가 증시 영업일인지 (주말·휴장일이 아닌지).

    시각과 무관하게 '날짜' 기준으로만 판정한다.
    장 운영시간까지 보려면 get_market_status()를 쓴다.
    """
    if check_date is None:
        check_date = now_kst().date()
    return check_date.weekday() < 5 and check_date not in HOLIDAYS


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
