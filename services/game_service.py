"""
예측게임 서비스 (리팩토링)
- 복권, 종목추첨, 등락예측, 업다운, 시장예측
- 장 마감 시간에만 플레이 가능 (복권 제외)
- 공통 유틸리티 사용으로 중복 제거
- 확률 상수화 및 검증
"""
import random
from datetime import datetime
from typing import Dict, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from config import GameConfig, GameProbability, ErrorCode, KST
from services.common import (
    get_user_with_error_for_update,
    validate_bet,
    check_market_closed_for_game,
    error_response,
    calculate_profit,
    safe_add,
    safe_multiply
)
from utils import get_service_logger, log_game

logger = get_service_logger()


class GameService:
    """예측게임 서비스"""

    @classmethod
    def play_lottery(cls, db: Session, kakao_id: str) -> Dict:
        """
        복권 긁기 (1일 5회, 무료)
        - 일일 제한이 있으므로 장 시간 무관하게 가능
        """
        user, error = get_user_with_error_for_update(db, kakao_id)
        if error:
            return error

        # 날짜가 바뀌었으면 카운트 리셋 (KST 기준)
        today = datetime.now(KST).date()
        if user.last_lottery_date != today:
            user.last_lottery_date = today
            user.lottery_count_today = 0

        # 오늘 최대 횟수 체크
        if user.lottery_count_today >= GameConfig.MAX_LOTTERY_PER_DAY:
            return error_response(
                ErrorCode.DAILY_LIMIT_REACHED,
                f"🎫 오늘 복권은 모두 긁었어요! ({GameConfig.MAX_LOTTERY_PER_DAY}회)\n내일 다시 도전하세요 🍀"
            )

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
            "5등": ("💫 5등", "소소하게!"),
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

        # 감사 로그
        log_game(
            kakao_id=kakao_id, game_type="LOTTERY",
            bet=0, result=tier,
            winnings=reward, profit=reward, cash_after=user.cash,
            extra=f"tier={tier_text}"
        )

        return {
            "success": True,
            "reward": reward,
            "tier": tier_text,
            "message": tier_msg,
            "cash": user.cash,
            "remaining": remaining
        }

    @classmethod
    def play_slot(cls, db: Session, kakao_id: str, bet: int = 50_000) -> Dict:
        """종목추첨 (투자금 필요)"""
        # 장 마감 시간에만 가능
        can_play, market_error = check_market_closed_for_game("📊")
        if not can_play:
            return market_error

        user, error = get_user_with_error_for_update(db, kakao_id)
        if error:
            return error

        # 투자금 검증
        is_valid, bet_error = validate_bet(bet, user.cash)
        if not is_valid:
            return error_response(ErrorCode.INVALID_BET, bet_error)

        # 투자금 차감
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

        # 종목추첨 심볼 생성
        slot1, slot2, slot3 = cls._generate_slot_symbols(outcome_symbol)

        # 수익금 계산 (오버플로우 방지)
        winnings = safe_multiply(bet, multiplier)
        user.cash = safe_add(user.cash, winnings)

        try:
            db.commit()
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"종목추첨 DB 커밋 실패: {e}")
            return error_response(ErrorCode.DB_ERROR, "데이터베이스 오류가 발생했습니다.")

        profit_info = calculate_profit(bet, winnings)

        # 감사 로그
        log_game(
            kakao_id=kakao_id, game_type="SLOT",
            bet=bet, result=outcome_symbol,
            winnings=winnings, profit=profit_info["profit"], cash_after=user.cash,
            extra=f"symbols={slot1}{slot2}{slot3} x{multiplier}"
        )

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
        """종목추첨 심볼 생성"""
        symbols = GameProbability.SLOT_SYMBOLS

        if outcome_symbol == "LOSE":
            # 손실: 모두 다른 심볼
            selected = random.sample(symbols, 3)
            return (selected[0], selected[1], selected[2])

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
        시장예측 (상승/하락/급등)
        - 상승: 2배 (50% 확률)
        - 하락: 2.5배 (40% 확률)
        - 급등: 10배 (10% 확률)
        """
        can_play, market_error = check_market_closed_for_game("🔮")
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
            return error_response(ErrorCode.INVALID_CHOICE, "상승, 하락, 급등 중 선택해주세요.")

        # 투자금 차감
        user.cash -= bet

        # 시장예측 결과 (GameProbability 사용)
        roll = random.random()
        cumulative = 0
        result = "상승"

        for direction, info in GameProbability.ROULETTE.items():
            cumulative += info["prob"]
            if roll < cumulative:
                result = direction
                break

        emoji_map = {"상승": "📈", "하락": "📉", "급등": "🚀"}
        emoji = emoji_map[result]

        # 적중 확인
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
            logger.error(f"시장예측 DB 커밋 실패: {e}")
            return error_response(ErrorCode.DB_ERROR, "데이터베이스 오류가 발생했습니다.")

        # 감사 로그
        log_game(
            kakao_id=kakao_id, game_type="ROULETTE",
            bet=bet, result=f"{result}({'WIN' if won else 'LOSE'})",
            winnings=winnings, profit=winnings - bet, cash_after=user.cash,
            extra=f"choice={choice_normalized} result={result}"
        )

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
        """시장예측 선택 정규화"""
        choice = choice.lower().strip()
        if choice in ["상승", "상", "up", "bull"]:
            return "상승"
        elif choice in ["하락", "하", "down", "bear"]:
            return "하락"
        elif choice in ["급등", "급", "boom", "surge"]:
            return "급등"
        return ""

    @classmethod
    def play_high_low(cls, db: Session, kakao_id: str, bet: int, choice: str) -> Dict:
        """
        업다운 예측게임
        - 1-100 숫자 중 50보다 높은지 낮은지
        """
        can_play, market_error = check_market_closed_for_game("🔢")
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
            return error_response(ErrorCode.INVALID_CHOICE, "상승/하락 중 선택해주세요.")

        # 투자금 차감
        user.cash -= bet

        # 숫자 뽑기 (1-100, 50은 무승부)
        number = random.randint(1, 100)

        if number == 50:
            # 무승부 - 투자금 반환
            user.cash += bet
            try:
                db.commit()
            except SQLAlchemyError as e:
                db.rollback()
                logger.error(f"업다운 무승부 DB 커밋 실패: {e}")
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
                "message": "무승부! 투자금 반환"
            }

        actual = "상승" if number > 50 else "하락"
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
            logger.error(f"업다운 DB 커밋 실패: {e}")
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
        """업다운 선택 정규화"""
        choice = choice.lower().strip()
        if choice in ["상승", "상", "high", "높", "하이", "up"]:
            return "상승"
        elif choice in ["하락", "하", "low", "낮", "로우", "down"]:
            return "하락"
        return ""

    @classmethod
    def play_coin_flip(cls, db: Session, kakao_id: str, bet: int, choice: str) -> Dict:
        """
        등락예측
        - 오름/내림 맞추면 2배 (기대값 100%)
        """
        can_play, market_error = check_market_closed_for_game("📉")
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
            return error_response(ErrorCode.INVALID_CHOICE, "오름/내림 중 선택해주세요.")

        # 투자금 차감
        user.cash -= bet

        # 등락 결과
        result = random.choice(["오름", "내림"])
        emoji = "📈" if result == "오름" else "📉"

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
            logger.error(f"등락예측 DB 커밋 실패: {e}")
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
        """등락예측 선택 정규화"""
        choice = choice.lower().strip()
        if choice in ["오름", "상승", "up", "앞", "앞면"]:
            return "오름"
        elif choice in ["내림", "하락", "down", "뒤", "뒷면"]:
            return "내림"
        return ""
