"""
증시 휴장일/영업일 판정 테스트

휴장일 데이터는 손으로 관리하므로 회귀가 나기 쉽다.
알려진 날짜를 고정해 두고, 데이터 갱신 시 깨지도록 한다.

증시 휴장일 = 법정공휴일 + KRX 전용 휴장일(근로자의 날, 연말 휴장)
"""

from datetime import date

import pytest

from market_calendar import (
    COVERED_YEARS,
    HOLIDAYS,
    KRX_ONLY_CLOSURES,
    PUBLIC_HOLIDAYS,
    has_holiday_data,
    is_holiday,
    is_trading_day,
)


class TestKrxOnlyClosures:
    """법정공휴일이 아니지만 증시는 쉬는 날 — 예전에 전부 빠져 있었다"""

    @pytest.mark.parametrize(
        "day",
        [date(2024, 5, 1), date(2025, 5, 1), date(2026, 5, 1)],
    )
    def test_labor_day_is_closed(self, day):
        """근로자의 날(5/1)은 법정공휴일이 아니지만 KRX는 휴장한다"""
        assert is_trading_day(day) is False, f"{day} 근로자의 날이 영업일로 판정됐다"

    @pytest.mark.parametrize(
        "day",
        [date(2024, 12, 31), date(2025, 12, 31), date(2026, 12, 31)],
    )
    def test_year_end_is_closed(self, day):
        """연말 휴장일(그 해 마지막 영업일)"""
        assert is_trading_day(day) is False, f"{day} 연말 휴장일이 영업일로 판정됐다"

    def test_labor_day_is_not_a_public_holiday(self):
        """분류가 섞이면 연말 휴장 계산이 어긋난다"""
        assert date(2025, 5, 1) not in PUBLIC_HOLIDAYS
        assert date(2025, 5, 1) in KRX_ONLY_CLOSURES

    def test_year_end_is_not_a_public_holiday(self):
        """
        연말 휴장을 법정공휴일로 분류하면 '마지막 영업일' 계산이 하루 앞당겨져
        실제 영업일(2024-12-30)을 휴장으로 잘못 판정한다.
        """
        assert date(2024, 12, 31) not in PUBLIC_HOLIDAYS
        assert date(2024, 12, 31) in KRX_ONLY_CLOSURES
        assert is_trading_day(date(2024, 12, 30)) is True


class TestElectionAndRestoredHolidays:
    def test_local_election_day_2026_is_closed(self):
        """2026-06-03 제9회 전국동시지방선거일"""
        assert is_trading_day(date(2026, 6, 3)) is False

    def test_constitution_day_2026_is_closed(self):
        """2026-07-17 제헌절 (공휴일 재지정)"""
        assert is_trading_day(date(2026, 7, 17)) is False

    def test_general_election_day_2024_is_closed(self):
        assert is_trading_day(date(2024, 4, 10)) is False


class TestOrdinaryDays:
    """휴장일을 과잉으로 잡지 않는지 (반대 방향 회귀 방지)"""

    @pytest.mark.parametrize(
        "day",
        [
            date(2026, 5, 4),  # 근로자의 날 다음 영업일(월)
            date(2026, 7, 16),  # 제헌절 전날(목)
            date(2026, 6, 2),  # 지방선거 전날(화)
            date(2025, 12, 30),  # 연말 휴장 전날(화)
            date(2026, 3, 3),  # 평범한 화요일
        ],
    )
    def test_regular_weekday_is_trading_day(self, day):
        assert is_trading_day(day) is True, f"{day}가 휴장으로 잘못 판정됐다"

    def test_weekend_is_not_trading_day(self):
        assert is_trading_day(date(2026, 5, 2)) is False  # 토
        assert is_trading_day(date(2026, 5, 3)) is False  # 일


class TestHolidayData:
    def test_holidays_is_union_of_both_sources(self):
        assert HOLIDAYS == PUBLIC_HOLIDAYS | KRX_ONLY_CLOSURES

    def test_covered_years_are_contiguous(self):
        years = sorted(COVERED_YEARS)
        assert years == list(range(years[0], years[-1] + 1))

    def test_every_covered_year_has_labor_day_and_year_end(self):
        for year in COVERED_YEARS:
            assert date(year, 5, 1) in HOLIDAYS, f"{year} 근로자의 날 누락"
            december = {
                d for d in KRX_ONLY_CLOSURES if d.year == year and d.month == 12
            }
            assert december, f"{year} 연말 휴장일 누락"

    def test_is_holiday_matches_holidays_set(self):
        assert is_holiday(date(2026, 1, 1)) is True
        assert is_holiday(date(2026, 5, 1)) is True
        assert is_holiday(date(2026, 3, 3)) is False

    def test_has_holiday_data_reports_coverage(self):
        assert has_holiday_data(max(COVERED_YEARS)) is True
        assert has_holiday_data(max(COVERED_YEARS) + 1) is False
