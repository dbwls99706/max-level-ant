"""
각성(강화) 시스템 설정

레벨이 오를수록 캐릭터가 진화하여 출석/복권 보상이 증가한다.
실패 시 레벨이 0으로 초기화되며, 장 마감 후에만 각성을 시도할 수 있다.

칭호·문구 데이터는 enhance_titles 모듈에 있다.
"""

import random
from typing import List, Optional, Tuple

from enhance_titles import (
    CLASS_INFO,
    CLASS_TITLES,
    FAIL_FLAVORS,
    SUCCESS_FLAVORS,
    TITLE_NAMES,
)

# 기본 칭호 (레벨 데이터가 없을 때 폴백)
DEFAULT_TITLE = ("투자자", "📊")


class EnhanceConfig:
    """각성 비용·확률·보상 배율 및 칭호 조회"""

    MAX_LEVEL = 20

    # 각성 비용: (현재 레벨 + 1) * BASE_COST
    BASE_COST = 100_000  # 10만원

    # 레벨별 성공 확률 (%) — 레벨 0→1 부터 19→20
    SUCCESS_RATES = [
        95,
        90,
        85,
        80,
        75,  # 0→1 ~ 4→5
        65,
        60,
        55,
        50,
        45,  # 5→6 ~ 9→10
        38,
        32,
        26,
        22,
        18,  # 10→11 ~ 14→15
        14,
        11,
        8,
        6,
        4,  # 15→16 ~ 19→20
    ]

    # 실패 시 레벨 0으로 초기화 (하드코어 모드)
    FAIL_RESET_TO_ZERO = True

    # 보너스 비율 (레벨당)
    ATTENDANCE_BONUS_PER_LEVEL = 0.05  # 출석: 레벨당 +5% (레벨 20 = +100%)
    LOTTERY_BONUS_PER_LEVEL = 0.08  # 복권: 레벨당 +8% (레벨 20 = +160%)

    # 직군 배정 레벨 (레벨 9 → 10 각성 성공 시 3개 직군 중 하나 랜덤 배정)
    CLASS_LEVEL_THRESHOLD = 10

    # 데이터 테이블 (enhance_titles) — 기존 호출부 호환을 위해 클래스 속성으로 노출
    SUCCESS_FLAVORS = SUCCESS_FLAVORS
    FAIL_FLAVORS = FAIL_FLAVORS
    TITLE_NAMES = TITLE_NAMES
    CLASS_INFO = CLASS_INFO
    CLASS_TITLES = CLASS_TITLES

    @classmethod
    def get_cost(cls, current_level: int) -> int:
        """각성 비용 계산"""
        return (current_level + 1) * cls.BASE_COST

    @classmethod
    def get_success_rate(cls, current_level: int) -> int:
        """현재 레벨에서 각성 성공률 (%)"""
        if current_level >= cls.MAX_LEVEL:
            return 0
        if current_level < 0:
            return cls.SUCCESS_RATES[0]
        return cls.SUCCESS_RATES[current_level]

    @classmethod
    def get_fail_penalty(cls, current_level: int) -> Tuple[int, int]:
        """실패 시 페널티 — 항상 레벨 0으로 초기화"""
        if current_level <= 0:
            return 0, 0
        return 100, current_level  # 100% 확률로 현재 레벨만큼 하락 = 0으로

    @classmethod
    def get_class_candidates(
        cls, level: int, enhance_class: int
    ) -> Optional[List[Tuple[str, str]]]:
        """직군 칭호 후보 반환. 해당 레벨·직군 없으면 None."""
        class_data = cls.CLASS_TITLES.get(enhance_class)
        if class_data is None:
            return None
        return class_data.get(level)

    @classmethod
    def get_title(
        cls, level: int, seed: Optional[int] = None, enhance_class: int = 0
    ) -> Tuple[str, str]:
        """레벨에 해당하는 칭호와 이모지.
        - level >= CLASS_LEVEL_THRESHOLD && enhance_class 배정 시 직군 칭호 사용
        - seed 있으면 해당 인덱스로 고정, 없으면 랜덤
        - level 20은 직군 무관 공통 만렙 칭호
        """
        level = max(0, min(level, cls.MAX_LEVEL))

        candidates = None
        # 레벨 20은 항상 공통 만렙 칭호
        if cls.CLASS_LEVEL_THRESHOLD <= level < cls.MAX_LEVEL and enhance_class:
            candidates = cls.get_class_candidates(level, enhance_class)

        if candidates is None:
            candidates = cls.TITLE_NAMES.get(level) or [DEFAULT_TITLE]

        if seed is not None:
            return candidates[seed % len(candidates)]
        return random.choice(candidates)

    @classmethod
    def get_attendance_multiplier(cls, level: int) -> float:
        """출석 보상 배율"""
        return 1.0 + (level * cls.ATTENDANCE_BONUS_PER_LEVEL)

    @classmethod
    def get_lottery_multiplier(cls, level: int) -> float:
        """복권 보상 배율"""
        return 1.0 + (level * cls.LOTTERY_BONUS_PER_LEVEL)
