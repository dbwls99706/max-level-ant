"""
게임 밸런스 설정
- 초기 자금, 보상, 수수료, 거래 한도 (GameConfig)
- 확률 테이블 및 기대값 검증 (GameProbability)

퀴즈 문제 데이터는 quiz_history 모듈에 있다.
"""

import logging

from quiz_history import HISTORICAL_STOCK_DATA

logger = logging.getLogger(__name__)


class GameConfig:
    """게임 밸런스 값"""

    # 초기 자금
    INITIAL_CASH = 10_000_000  # 1000만원

    # 출석 보상
    ATTENDANCE_REWARD = 300_000  # 30만원
    ATTENDANCE_STREAK_BONUS = {
        3: 1.2,  # 3일 연속: 20% 보너스
        5: 1.5,  # 5일 연속: 50% 보너스
        7: 2.0,  # 7일 연속: 100% 보너스 (최대 60만원)
    }

    # 광고 보상 (비활성화 - 수익 발생 방지)
    AD_DISABLED = True

    # 거래 수수료
    TRADE_FEE_RATE = 0.001  # 0.1%

    # 최소 거래 단위
    MIN_TRADE_AMOUNT = 1  # 최소 1주

    # 일간 미션
    DAILY_MISSION_TRADE_COUNT = 3  # 3번 거래 미션
    DAILY_MISSION_REWARD = 200_000  # 20만원

    # 주간 보너스 (특정 요일)
    WEEKLY_BONUS_DAY = 0  # 월요일 (0=월, 6=일)
    WEEKLY_BONUS_MULTIPLIER = 2.0  # 2배 보너스

    # 예측게임/투자 설정
    MIN_BET = 10_000  # 최소 투자금 1만원
    MAX_BET = 999_999_999_999  # 최대 투자금 9999억 9999만 9999원
    DEFAULT_BET = 50_000  # 기본 투자금 5만원
    BIG_BET = 500_000  # 큰 투자금 50만원 (게임 메뉴용)
    DEFAULT_BATTLE_BET = 100_000  # 배틀 기본 투자금 10만원
    LOTTERY_COST = 0  # 복권 가격 (무료)
    MAX_LOTTERY_PER_DAY = 5  # 복권 1일 최대 횟수

    # 배틀 투자금 한도 (1:1 대결)
    BATTLE_MIN_BET = 10_000  # 1만원
    BATTLE_MAX_BET = 100_000_000  # 1억

    # 투자금 검증 기본 상한 (호출부가 별도 한도를 주지 않을 때)
    DEFAULT_BET_CAP = 10_000_000_000  # 100억

    # 거래 설정
    MAX_QUANTITY = 1_000_000  # 1회 최대 거래 수량
    MAX_CASH = 10_000_000_000_000  # 최대 현금 10조 (오버플로우 방지)

    # 검색 제한 (카카오톡 메시지 1000자 제한 고려, KIS API 최대 10개 반환)
    MAX_SEARCH_LIMIT = 20  # 검색 결과 최대 개수


class GameProbability:
    """
    게임 확률 상수 (기대값 검증 포함)

    모든 확률은 합이 1.0이어야 하며,
    기대값(EV)은 합리적인 범위 내에 있어야 합니다.
    """

    # 보물상자 희귀도 확률 (전설→빈상자 순, 기대값 ~100%)
    LOTTERY = {
        "전설": {"prob": 0.003, "min_reward": 500_000, "max_reward": 1_000_000},  # 0.3%
        "영웅": {"prob": 0.025, "min_reward": 50_000, "max_reward": 100_000},  # 2.5%
        "희귀": {"prob": 0.070, "min_reward": 15_000, "max_reward": 30_000},  # 7.0%
        "고급": {"prob": 0.120, "min_reward": 12_000, "max_reward": 20_000},  # 12.0%
        "일반": {"prob": 0.470, "min_reward": 3_000, "max_reward": 8_000},  # 47.0%
        "빈 상자": {"prob": 0.312, "min_reward": 0, "max_reward": 0},  # 31.2%
    }

    # 시장예측 (역사 퀴즈) - 상승/하락 맞추면 x2 (기대값: 지식 의존)
    STOCK_QUIZ_MULTIPLIER = 2.0

    # 역사 퀴즈 데이터 (quiz_history)
    HISTORICAL_STOCK_DATA = HISTORICAL_STOCK_DATA

    # 역사 퀴즈 최소 문항 수 (검증용)
    MIN_QUIZ_COUNT = 10

    # 업다운 멀티라운드 - 배율은 확률 기반으로 동적 계산
    # (EV 100%: 매 라운드 배율 = 1/확률)
    # 라운드 진행 수수료: 정보 우위를 상쇄하기 위한 배율 감소
    UPDOWN_ROUND_FEE = {
        # (시작 라운드, 끝 라운드): 배율 유지율
        (1, 3): 1.0,  # 1~3라운드: 수수료 없음 (신규 유저 체험)
        (4, 6): 0.95,  # 4~6라운드: 배율 5% 차감
        (7, 9): 0.90,  # 7~9라운드: 배율 10% 차감
        (10, 99): 0.85,  # 10라운드+: 배율 15% 차감
    }

    @classmethod
    def validate_probabilities(cls) -> bool:
        """모든 확률이 유효한지 검증"""
        errors = []

        # 복권 확률 합계 검증
        lottery_sum = sum(tier["prob"] for tier in cls.LOTTERY.values())
        if not (0.999 <= lottery_sum <= 1.001):
            errors.append(f"복권 확률 합계 오류: {lottery_sum}")

        # 역사 퀴즈 데이터 검증
        if len(cls.HISTORICAL_STOCK_DATA) < cls.MIN_QUIZ_COUNT:
            errors.append(f"역사 퀴즈 데이터 부족: {len(cls.HISTORICAL_STOCK_DATA)}개")

        up_count = sum(1 for q in cls.HISTORICAL_STOCK_DATA if q["answer"] == "상승")
        down_count = len(cls.HISTORICAL_STOCK_DATA) - up_count
        if up_count == 0 or down_count == 0:
            errors.append("역사 퀴즈 데이터에 상승/하락이 균형적이지 않음")

        if errors:
            for error in errors:
                logger.warning(f"확률 검증 실패: {error}")
            return False

        logger.debug("게임 확률 검증 완료")
        return True

    @classmethod
    def calculate_expected_value(cls, game: str) -> float:
        """게임별 기대값 계산 (%)"""
        if game == "lottery":
            if GameConfig.LOTTERY_COST == 0:
                return 100.0
            cost = GameConfig.LOTTERY_COST
            ev = 0
            for tier in cls.LOTTERY.values():
                avg_reward = (tier["min_reward"] + tier["max_reward"]) / 2
                ev += tier["prob"] * avg_reward
            return (ev / cost) * 100

        if game == "stock_quiz":
            # 역사 퀴즈 기대값 (지식 의존, 50% 기준)
            return 0.5 * cls.STOCK_QUIZ_MULTIPLIER * 100

        if game == "updown":
            # 업다운 멀티라운드 - 매 라운드 EV = 100% (배율 = 1/확률)
            return 100.0

        return 0
