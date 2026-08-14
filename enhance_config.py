"""
각성(강화) 시스템 설정

레벨이 오를수록 캐릭터가 진화하여 출석/복권 보상이 증가한다.
실패 시 레벨과 계열이 모두 0으로 초기화된다.

각성은 장 마감 후에만 시도할 수 있다. 이 제한은 서비스가 아니라 핸들러
(`GameHandlerMixin._do_enhance`)가 `check_market_closed_for_game`으로 건다.
장중에는 시세와 매매에 집중시키기 위한 것이고, 장외 시간은 하루의 대부분이라
사실상의 관문은 시각이 아니라 비용이다. 그 돈은 주식으로 번다.

이 게임의 중심은 수익률이지 각성이 아니므로 비용은 의도적으로 낮게 잡혀 있다.

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

    MAX_LEVEL = 30

    # 각성 비용: BASE_COST + 현재 레벨 * COST_PER_LEVEL
    #
    # 예전에는 (레벨+1) * 10만원이라 Lv.15 한 번에 160만원이었다. 하루 고정
    # 수입이 55만원 남짓인데 시도 한 번이 사흘치라, 각성을 하려면 사실상
    # 각성 전용 재화를 따로 모으는 게임이 되어버린다.
    #
    # 이 게임의 중심은 주식 수익률이지 각성이 아니다. 각성은 곁다리 성장
    # 요소이므로 시도 한 번이 하루 수입 안에서 여러 번 감당돼야 한다.
    # 만렙 직전에도 9.7만원으로, 예전 Lv.19 비용(200만원)의 20분의 1이다.
    BASE_COST = 10_000
    COST_PER_LEVEL = 3_000

    # 레벨별 성공 확률 (%) - 레벨 0→1 부터 29→30
    #
    # 실패하면 무조건 0으로 떨어지므로 Lv.N 도달 확률은 N개 확률의 곱이다.
    # 곱이라 개별 확률을 조금만 내려도 도달 확률이 무너진다. 예전 곡선은
    # 후반이 4~18%라 Lv.20 도달 확률이 128억분의 1, 기대비용 2.4경원이었다.
    # 도감·칭호 같은 상위 콘텐츠가 통째로 사장되는 값이다.
    #
    # 그래서 초반은 사실상 통과시키고 후반에서만 갈리게 잡았다.
    # 실측 기대치: Lv.10 하루, Lv.20 나흘, Lv.30 약 72일 (매매 손익 제외).
    SUCCESS_RATES = [
        99, 98, 98, 97, 96, 96, 95, 94, 94, 93,  # 0→1 ~ 9→10    Lv.10 도달 66.4%
        92, 91, 90, 90, 89, 88, 87, 87, 86, 85,  # 10→11 ~ 19→20 Lv.20 도달 19.5%
        84, 82, 80, 79, 77, 75, 73, 72, 70, 68,  # 20→21 ~ 29→30 Lv.30 도달  1.2%
    ]  # fmt: skip

    # 실패 시 레벨 0으로 초기화 (하드코어 모드).
    # 계열도 같이 풀려서 다음에 Lv.10에 도달할 때 새로 뽑는다.
    FAIL_RESET_TO_ZERO = True

    # 보너스 비율 (레벨당)
    ATTENDANCE_BONUS_PER_LEVEL = 0.05  # 출석: 레벨당 +5% (레벨 20 = +100%)
    LOTTERY_BONUS_PER_LEVEL = 0.08  # 복권: 레벨당 +8% (레벨 20 = +160%)

    # 직군 배정 레벨 (레벨 9 → 10 각성 성공 시 3개 직군 중 하나 랜덤 배정)
    CLASS_LEVEL_THRESHOLD = 10

    # 데이터 테이블 (enhance_titles) - 기존 호출부 호환을 위해 클래스 속성으로 노출
    SUCCESS_FLAVORS = SUCCESS_FLAVORS
    FAIL_FLAVORS = FAIL_FLAVORS
    TITLE_NAMES = TITLE_NAMES
    CLASS_INFO = CLASS_INFO
    CLASS_TITLES = CLASS_TITLES

    @classmethod
    def get_cost(cls, current_level: int) -> int:
        """각성 비용 계산"""
        return cls.BASE_COST + max(0, current_level) * cls.COST_PER_LEVEL

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
        """실패 시 페널티 - 항상 레벨 0으로 초기화"""
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
