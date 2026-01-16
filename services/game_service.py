"""
미니게임 서비스 (리팩토링)
- 복권, 슬롯, 동전, 하이로우, 룰렛
- 장 마감 시간에만 플레이 가능 (복권 제외)
- 공통 유틸리티 사용으로 중복 제거
- 확률 상수화 및 검증
"""
import random
from datetime import date
from typing import Dict, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from config import GameConfig, GameProbability, ErrorCode
from services.common import (
    get_user_with_error,
    get_user_with_error_for_update,
    validate_bet,
    check_market_closed_for_game,
    error_response,
    calculate_profit,
    safe_add,
    safe_multiply
)
from utils import get_service_logger

logger = get_service_logger()


class GameService:
    """미니게임 서비스"""

    @classmethod
    def play_lottery(cls, db: Session, kakao_id: str) -> Dict:
        """
        복권 긁기 (1일 5회, 1장 10,000원)
        - 일일 제한이 있으므로 장 시간 무관하게 가능
        """
        user, error = get_user_with_error_for_update(db, kakao_id)
        if error:
            return error

        # 날짜가 바뀌었으면 카운트 리셋
        today = date.today()
        if user.last_lottery_date != today:
            user.last_lottery_date = today
            user.lottery_count_today = 0

        # 오늘 최대 횟수 체크
        if user.lottery_count_today >= GameConfig.MAX_LOTTERY_PER_DAY:
            return error_response(
                ErrorCode.DAILY_LIMIT_REACHED,
                f"🎫 오늘 복권은 모두 긁었어요! ({GameConfig.MAX_LOTTERY_PER_DAY}회)\n내일 다시 도전하세요 🍀"
            )

        # 잔액 확인
        if user.cash < GameConfig.LOTTERY_COST:
            return error_response(
                ErrorCode.INSUFFICIENT_BALANCE,
                f"❌ 잔액 부족!\n복권 가격: {GameConfig.LOTTERY_COST:,}원\n보유: {user.cash:,}원"
            )

        # 복권 구매 (비용 차감)
        user.cash -= GameConfig.LOTTERY_COST
        user.lottery_count_today += 1
        remaining = GameConfig.MAX_LOTTERY_PER_DAY - user.lottery_count_today

        # 확률 기반 결과 결정 (GameProbability 사용)
        roll = random.random()
        cumulative = 0
        tier = "꽝"
        reward = 0

        tier_display = {
            "1등": ("🥇 1등", "대박! 축하합니다!"),
            "2등": ("🥈 2등", "좋아요!"),
            "3등": ("🥉 3등", "괜찮네요!"),
            "4등": ("🎁 4등", "조금이나마..."),
            "5등": ("💫 5등", "본전!"),
            "꽝": ("😅 꽝", "다음 기회에..."),
        }

        for tier_name, tier_info in GameProbability.LOTTERY.items():
            cumulative += tier_info["prob"]
            if roll < cumulative:
                tier = tier_name
                reward = random.randint(tier_info["min_reward"], tier_info["max_reward"])
                break

        tier_text, tier_msg = tier_display.get(tier, ("😅 꽝", "다음 기회에..."))

        # 보상 지급 (오버플로우 방지)
        user.cash = safe_add(user.cash, reward)

        # 트랜잭션 커밋
        try:
            db.commit()
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"복권 DB 커밋 실패: {e}")
            return error_response(ErrorCode.DB_ERROR, "데이터베이스 오류가 발생했습니다.")

        profit = reward - GameConfig.LOTTERY_COST

        return {
            "success": True,
            "cost": GameConfig.LOTTERY_COST,
            "reward": reward,
            "profit": profit,
            "tier": tier_text,
            "message": tier_msg,
            "cash": user.cash,
            "remaining": remaining
        }

    @classmethod
    def play_slot(cls, db: Session, kakao_id: str, bet: int = 50_000) -> Dict:
        """슬롯머신 (배팅 금액 필요)"""
        # 장 마감 시간에만 가능
        can_play, market_error = check_market_closed_for_game("🎰")
        if not can_play:
            return market_error

        user, error = get_user_with_error_for_update(db, kakao_id)
        if error:
            return error

        # 배팅금 검증
        is_valid, bet_error = validate_bet(bet, user.cash)
        if not is_valid:
            return error_response(ErrorCode.INVALID_BET, bet_error)

        # 배팅금 차감
        user.cash -= bet

        # 확률 기반 결과 결정 (GameProbability 사용)
        roll = random.random()
        cumulative = 0
        outcome_symbol = "LOSE"
        multiplier = 0

        for symbol, mult, prob in GameProbability.SLOT_PAYOUTS:
            cumulative += prob
            if roll < cumulative:
                outcome_symbol = symbol
                multiplier = mult
                break

        # 슬롯 심볼 생성
        slot1, slot2, slot3 = cls._generate_slot_symbols(outcome_symbol)

        # 당첨금 계산 (오버플로우 방지)
        winnings = safe_multiply(bet, multiplier)
        user.cash = safe_add(user.cash, winnings)

        try:
            db.commit()
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"슬롯 DB 커밋 실패: {e}")
            return error_response(ErrorCode.DB_ERROR, "데이터베이스 오류가 발생했습니다.")

        profit_info = calculate_profit(bet, winnings)

        return {
            "success": True,
            "slots": [slot1, slot2, slot3],
            "result": f"{slot1}{slot2}{slot3}",
            "bet": bet,
            "multiplier": multiplier,
            "winnings": winnings,
            "profit": profit_info["profit"],
            "cash": user.cash,
            "jackpot": multiplier >= 20
        }

    @classmethod
    def _generate_slot_symbols(cls, outcome_symbol: str) -> Tuple[str, str, str]:
        """슬롯 심볼 생성"""
        symbols = GameProbability.SLOT_SYMBOLS

        if outcome_symbol == "LOSE":
            # 꽝: 모두 다른 심볼
            selected = random.sample(symbols, 3)
            return tuple(selected)

        elif outcome_symbol == "MATCH2":
            # 2개 일치 (본전)
            match_symbol = random.choice(symbols)
            other_symbols = [s for s in symbols if s != match_symbol]
            other = random.choice(other_symbols)
            pattern = random.choice([
                (match_symbol, match_symbol, other),
                (match_symbol, other, match_symbol),
                (other, match_symbol, match_symbol)
            ])
            return pattern

        else:
            # 3개 일치
            return (outcome_symbol, outcome_symbol, outcome_symbol)

    @classmethod
    def play_roulette(cls, db: Session, kakao_id: str, bet: int, choice: str) -> Dict:
        """
        룰렛 (빨강/검정/초록)
        - 빨강/검정: 2배 (45% 확률)
        - 초록: 9배 (10% 확률)
        """
        can_play, market_error = check_market_closed_for_game("🎡")
        if not can_play:
            return market_error

        user, error = get_user_with_error_for_update(db, kakao_id)
        if error:
            return error

        is_valid, bet_error = validate_bet(bet, user.cash)
        if not is_valid:
            return error_response(ErrorCode.INVALID_BET, bet_error)

        # 선택 정규화
        choice_normalized = cls._normalize_roulette_choice(choice)
        if not choice_normalized:
            return error_response(ErrorCode.INVALID_CHOICE, "빨강, 검정, 초록 중 선택해주세요.")

        # 배팅금 차감
        user.cash -= bet

        # 룰렛 결과 (GameProbability 사용)
        roll = random.random()
        cumulative = 0
        result = "빨강"

        for color, info in GameProbability.ROULETTE.items():
            cumulative += info["prob"]
            if roll < cumulative:
                result = color
                break

        emoji_map = {"빨강": "🔴", "검정": "⚫", "초록": "🟢"}
        emoji = emoji_map[result]

        # 당첨 확인
        won = (choice_normalized == result)

        if won:
            multiplier = GameProbability.ROULETTE[result]["multiplier"]
            winnings = safe_multiply(bet, multiplier)
        else:
            multiplier = 0
            winnings = 0

        user.cash = safe_add(user.cash, winnings)

        try:
            db.commit()
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"룰렛 DB 커밋 실패: {e}")
            return error_response(ErrorCode.DB_ERROR, "데이터베이스 오류가 발생했습니다.")

        return {
            "success": True,
            "result": result,
            "emoji": emoji,
            "choice": choice_normalized,
            "won": won,
            "bet": bet,
            "multiplier": multiplier,
            "winnings": winnings,
            "profit": winnings - bet,
            "cash": user.cash
        }

    @classmethod
    def _normalize_roulette_choice(cls, choice: str) -> str:
        """룰렛 선택 정규화"""
        choice = choice.lower().strip()
        if choice in ["red", "빨강", "빨"]:
            return "빨강"
        elif choice in ["black", "검정", "검"]:
            return "검정"
        elif choice in ["green", "초록", "초"]:
            return "초록"
        return ""

    @classmethod
    def play_high_low(cls, db: Session, kakao_id: str, bet: int, choice: str) -> Dict:
        """
        하이로우 게임
        - 1-100 숫자 중 50보다 높은지 낮은지
        """
        can_play, market_error = check_market_closed_for_game("🎲")
        if not can_play:
            return market_error

        user, error = get_user_with_error_for_update(db, kakao_id)
        if error:
            return error

        is_valid, bet_error = validate_bet(bet, user.cash)
        if not is_valid:
            return error_response(ErrorCode.INVALID_BET, bet_error)

        # 선택 정규화
        choice_normalized = cls._normalize_highlow_choice(choice)
        if not choice_normalized:
            return error_response(ErrorCode.INVALID_CHOICE, "높/낮 중 선택해주세요.")

        # 배팅금 차감
        user.cash -= bet

        # 숫자 뽑기 (1-100, 50은 무승부)
        number = random.randint(1, 100)

        if number == 50:
            # 무승부 - 배팅금 반환
            user.cash += bet
            try:
                db.commit()
            except SQLAlchemyError as e:
                db.rollback()
                logger.error(f"하이로우 무승부 DB 커밋 실패: {e}")
                return error_response(ErrorCode.DB_ERROR, "데이터베이스 오류가 발생했습니다.")

            return {
                "success": True,
                "number": number,
                "choice": choice_normalized,
                "won": None,
                "bet": bet,
                "winnings": bet,
                "profit": 0,
                "cash": user.cash,
                "message": "무승부! 배팅금 반환"
            }

        actual = "높" if number > 50 else "낮"
        won = (choice_normalized == actual)

        if won:
            multiplier = GameProbability.HIGHLOW_MULTIPLIER
            winnings = safe_multiply(bet, multiplier)
        else:
            multiplier = 0
            winnings = 0

        user.cash = safe_add(user.cash, winnings)

        try:
            db.commit()
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"하이로우 DB 커밋 실패: {e}")
            return error_response(ErrorCode.DB_ERROR, "데이터베이스 오류가 발생했습니다.")

        return {
            "success": True,
            "number": number,
            "actual": actual,
            "choice": choice_normalized,
            "won": won,
            "bet": bet,
            "multiplier": multiplier if won else 0,
            "winnings": winnings,
            "profit": winnings - bet,
            "cash": user.cash
        }

    @classmethod
    def _normalize_highlow_choice(cls, choice: str) -> str:
        """하이로우 선택 정규화"""
        choice = choice.lower().strip()
        if choice in ["high", "높", "하이"]:
            return "높"
        elif choice in ["low", "낮", "로우"]:
            return "낮"
        return ""

    @classmethod
    def play_coin_flip(cls, db: Session, kakao_id: str, bet: int, choice: str) -> Dict:
        """
        동전 던지기
        - 앞/뒤 맞추면 2배 (기대값 100%)
        """
        can_play, market_error = check_market_closed_for_game("🪙")
        if not can_play:
            return market_error

        user, error = get_user_with_error_for_update(db, kakao_id)
        if error:
            return error

        is_valid, bet_error = validate_bet(bet, user.cash)
        if not is_valid:
            return error_response(ErrorCode.INVALID_BET, bet_error)

        # 선택 정규화
        choice_normalized = cls._normalize_coin_choice(choice)
        if not choice_normalized:
            return error_response(ErrorCode.INVALID_CHOICE, "앞/뒤 중 선택해주세요.")

        # 배팅금 차감
        user.cash -= bet

        # 동전 던지기
        result = random.choice(["앞", "뒤"])
        emoji = "🪙" if result == "앞" else "💿"

        won = (choice_normalized == result)

        if won:
            multiplier = GameProbability.COINFLIP_MULTIPLIER
            winnings = safe_multiply(bet, multiplier)
        else:
            multiplier = 0
            winnings = 0

        user.cash = safe_add(user.cash, winnings)

        try:
            db.commit()
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"동전 DB 커밋 실패: {e}")
            return error_response(ErrorCode.DB_ERROR, "데이터베이스 오류가 발생했습니다.")

        return {
            "success": True,
            "result": result,
            "emoji": emoji,
            "choice": choice_normalized,
            "won": won,
            "bet": bet,
            "multiplier": multiplier if won else 0,
            "winnings": winnings,
            "profit": winnings - bet,
            "cash": user.cash
        }

    @classmethod
    def _normalize_coin_choice(cls, choice: str) -> str:
        """동전 선택 정규화"""
        choice = choice.lower().strip()
        if choice in ["head", "앞", "앞면"]:
            return "앞"
        elif choice in ["tail", "뒤", "뒷면"]:
            return "뒤"
        return ""
