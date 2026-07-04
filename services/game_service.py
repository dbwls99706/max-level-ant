"""
예측게임 서비스
- 복권, 시장예측(역사 퀴즈), 업다운(멀티라운드)
- 장 마감 시간에만 플레이 가능 (복권 제외)
"""
import json
import random
from datetime import datetime
from typing import Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from config import GameConfig, GameProbability, EnhanceConfig, ErrorCode, KST
from services.common import (
    get_user_with_error_for_update,
    validate_bet,
    check_market_closed_for_game,
    error_response,
    safe_add,
    safe_subtract,
    safe_multiply
)
from utils import get_service_logger, log_game

logger = get_service_logger()


class GameService:
    """예측게임 서비스"""

    # ==========================================
    # 복권 (변경 없음)
    # ==========================================

    @classmethod
    def play_lottery(cls, db: Session, kakao_id: str) -> Dict:
        """
        복권 긁기 (1일 5회, 무료)
        - 일일 제한이 있으므로 장 시간 무관하게 가능
        """
        user, error = get_user_with_error_for_update(db, kakao_id)
        if error:
            return error

        today = datetime.now(KST).date()
        if user.last_lottery_date != today:
            user.last_lottery_date = today
            user.lottery_count_today = 0

        if user.lottery_count_today >= GameConfig.MAX_LOTTERY_PER_DAY:
            return error_response(
                ErrorCode.DAILY_LIMIT_REACHED,
                f"🎁 오늘 보물상자를 모두 열었어요! ({GameConfig.MAX_LOTTERY_PER_DAY}회)\n내일 다시 도전하세요 🍀"
            )

        user.lottery_count_today += 1
        remaining = GameConfig.MAX_LOTTERY_PER_DAY - user.lottery_count_today

        roll = random.random()
        cumulative = 0
        tier = "빈 상자"
        reward = 0

        tier_display = {
            "전설":   ("🟠 전설",   "이게 실화?! 전설 등급 획득!"),
            "영웅":   ("🟣 영웅",   "오늘 운이 폭발했어요!"),
            "희귀":   ("🔵 희귀",   "희귀 아이템 획득!"),
            "고급":   ("🟢 고급",   "쏠쏠하네요!"),
            "일반":   ("⚪ 일반",   "소소한 행운!"),
            "빈 상자":("📦 빈 상자","다음엔 꼭 뜰 거예요..."),
        }

        for tier_name, tier_info in GameProbability.LOTTERY.items():
            cumulative += tier_info["prob"]
            if roll < cumulative:
                tier = tier_name
                reward = random.randint(tier_info["min_reward"], tier_info["max_reward"])
                break

        # 각성 보너스 적용 (꽝이 아닌 경우)
        enhance_level = getattr(user, 'enhance_level', 0) or 0
        enhance_bonus = 0
        if reward > 0 and enhance_level > 0:
            enhance_mult = EnhanceConfig.get_lottery_multiplier(enhance_level)
            enhanced_reward = int(reward * enhance_mult)
            enhance_bonus = enhanced_reward - reward
            reward = enhanced_reward

        tier_text, tier_msg = tier_display.get(tier, ("📦 빈 상자", "다음엔 꼭 뜰 거예요..."))

        # Near-miss 판정: 빈 상자일 때 바로 위 등급(일반) 경계에 얼마나 가까웠는지
        near_miss_tier = None
        near_miss_reward = 0
        if tier == "빈 상자":
            boundary = 1.0 - GameProbability.LOTTERY["빈 상자"]["prob"]
            distance = roll - boundary
            miss_ratio = distance / GameProbability.LOTTERY["빈 상자"]["prob"]

            # 경계 바로 아래 등급은 "일반" — 실제 인접 등급/보상으로 안내
            if miss_ratio < 0.15:
                near_miss_tier = "일반"
                near_miss_reward = GameProbability.LOTTERY["일반"]["max_reward"]

        user.cash = safe_add(user.cash, reward)

        try:
            db.commit()
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"복권 DB 커밋 실패: {e}")
            return error_response(ErrorCode.DB_ERROR, "데이터베이스 오류가 발생했습니다.")

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
            "remaining": remaining,
            "enhance_bonus": enhance_bonus,
            "enhance_level": enhance_level,
            "near_miss_tier": near_miss_tier,
            "near_miss_reward": near_miss_reward,
        }

    # ==========================================
    # 시장예측 — 역사 퀴즈
    # ==========================================

    @classmethod
    def issue_stock_quiz(cls, db: Session, kakao_id: str, bet: int) -> Dict:
        """
        시장예측 퀴즈 출제
        - 서버가 랜덤 퀴즈를 뽑아 유저에 저장 (판정은 answer_stock_quiz에서 저장된 퀴즈로만)
        - 이미 출제된 퀴즈가 있으면 같은 퀴즈를 다시 안내 (퀴즈 골라잡기 방지)
        - 베팅 금액은 출제 시점에 고정
        """
        can_play, market_error = check_market_closed_for_game("🔮")
        if not can_play:
            return market_error

        user, error = get_user_with_error_for_update(db, kakao_id)
        if error:
            return error

        # 진행 중인 퀴즈가 있으면 재출제하지 않고 그대로 반환
        pending = cls._load_pending_quiz(user)
        if pending:
            return {
                "success": True,
                "quiz": pending,
                "bet": user.pending_quiz_bet,
                "reissued": True,
                "cash": user.cash,
            }

        is_valid, bet_error = validate_bet(bet, user.cash)
        if not is_valid:
            return error_response(ErrorCode.INVALID_BET, bet_error)

        # 랜덤 퀴즈 선택 (실제 주가 데이터 기반, 폴백: 하드코딩)
        from services.quiz_data_service import get_random_quiz
        quiz = get_random_quiz()

        user.pending_quiz = json.dumps(quiz, ensure_ascii=False)
        user.pending_quiz_bet = bet

        try:
            db.commit()
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"시장예측 출제 DB 커밋 실패: {e}")
            return error_response(ErrorCode.DB_ERROR, "데이터베이스 오류가 발생했습니다.")

        return {
            "success": True,
            "quiz": quiz,
            "bet": bet,
            "reissued": False,
            "cash": user.cash,
        }

    @classmethod
    def answer_stock_quiz(cls, db: Session, kakao_id: str, choice: str) -> Dict:
        """
        시장예측 퀴즈 판정
        - 서버가 출제해 저장한 퀴즈로만 판정 (유저가 퀴즈를 지정할 수 없음)
        - 판정 후 출제 상태 초기화 (1회용)
        """
        can_play, market_error = check_market_closed_for_game("🔮")
        if not can_play:
            return market_error

        user, error = get_user_with_error_for_update(db, kakao_id)
        if error:
            return error

        choice_normalized = cls._normalize_quiz_choice(choice)
        if not choice_normalized:
            return error_response(ErrorCode.INVALID_CHOICE, "상승 또는 하락 중 선택해주세요.")

        quiz = cls._load_pending_quiz(user)
        if not quiz:
            return error_response(
                ErrorCode.INVALID_STATE,
                "출제된 퀴즈가 없어요. /시장예측 [금액] 으로 먼저 퀴즈를 받아주세요!"
            )

        bet = user.pending_quiz_bet or 0
        is_valid, bet_error = validate_bet(bet, user.cash)
        if not is_valid:
            # 출제 후 잔고가 줄어 베팅 불가 — 출제 상태를 비우고 다시 받도록 안내
            user.pending_quiz = None
            user.pending_quiz_bet = 0
            db.commit()
            return error_response(ErrorCode.INVALID_BET, bet_error)

        # 투자금 차감
        user.cash = safe_subtract(user.cash, bet)

        # 정답 확인
        won = (choice_normalized == quiz["answer"])

        if won:
            multiplier = GameProbability.STOCK_QUIZ_MULTIPLIER
            winnings = safe_multiply(bet, multiplier)
        else:
            multiplier = 0
            winnings = 0

        user.cash = safe_add(user.cash, winnings)

        # 출제 상태 초기화 (판정과 같은 트랜잭션에서 원자적으로)
        user.pending_quiz = None
        user.pending_quiz_bet = 0

        try:
            db.commit()
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"시장예측 DB 커밋 실패: {e}")
            return error_response(ErrorCode.DB_ERROR, "데이터베이스 오류가 발생했습니다.")

        log_game(
            kakao_id=kakao_id, game_type="STOCK_QUIZ",
            bet=bet, result=f"{quiz['answer']}({'WIN' if won else 'LOSE'})",
            winnings=winnings, profit=winnings - bet, cash_after=user.cash,
            extra=f"stock={quiz['stock_name']} period={quiz['period']} choice={choice_normalized}"
        )

        return {
            "success": True,
            "quiz": quiz,
            "choice": choice_normalized,
            "answer": quiz["answer"],
            "won": won,
            "bet": bet,
            "multiplier": multiplier,
            "winnings": winnings,
            "profit": winnings - bet,
            "cash": user.cash
        }

    @staticmethod
    def _load_pending_quiz(user) -> Optional[Dict]:
        """유저에 저장된 출제 퀴즈 로드 (손상 시 None)"""
        if not user.pending_quiz:
            return None
        try:
            quiz = json.loads(user.pending_quiz)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"출제 퀴즈 파싱 실패: {user.kakao_id}")
            return None
        if not isinstance(quiz, dict) or quiz.get("answer") not in ("상승", "하락"):
            return None
        return quiz

    @classmethod
    def _normalize_quiz_choice(cls, choice: str) -> str:
        """시장예측 선택 정규화"""
        choice = choice.lower().strip()
        if choice in ["상승", "상", "up", "오름"]:
            return "상승"
        elif choice in ["하락", "하", "down", "내림"]:
            return "하락"
        return ""

    # ==========================================
    # 업다운 — 멀티라운드
    # ==========================================

    @classmethod
    def _round_fee_rate(cls, round_num: int) -> float:
        """해당 라운드의 배율 유지율 (수수료 적용)"""
        for (start_r, end_r), rate in GameProbability.UPDOWN_ROUND_FEE.items():
            if start_r <= round_num <= end_r:
                return rate
        return 1.0

    @classmethod
    def _preview_multipliers(cls, number: int, round_num: int):
        """
        다음 선택지 배율 미리 계산 (라운드 수수료 반영)
        Returns: (up_mult, down_mult, up_count, down_count)
        """
        up_count = 100 - number
        down_count = number - 1
        total = up_count + down_count
        fee_rate = cls._round_fee_rate(round_num)
        up_mult = round((total / up_count) * fee_rate, 2) if up_count > 0 else 99.0
        down_mult = round((total / down_count) * fee_rate, 2) if down_count > 0 else 99.0
        return up_mult, down_mult, up_count, down_count

    @classmethod
    def start_updown(cls, db: Session, kakao_id: str, bet: int) -> Dict:
        """
        업다운 게임 시작
        - 랜덤 숫자(1~100) 생성, 다음 숫자가 높을지 낮을지 맞추기
        - 맞추면 계속 진행, 틀리면 투자금 손실
        - 언제든 정산 가능
        """
        can_play, market_error = check_market_closed_for_game("🔢")
        if not can_play:
            return market_error

        user, error = get_user_with_error_for_update(db, kakao_id)
        if error:
            return error

        # 이미 진행중인 게임이 있으면 알림
        if user.updown_active:
            return {
                "success": False,
                "active_game": True,
                "message": f"🔢 이미 진행 중인 업다운 게임이 있어요!\n\n현재 숫자: {user.updown_current_number}\n라운드: {user.updown_round}\n누적 배율: x{user.updown_multiplier:.2f}\n투자금: {user.updown_bet:,}원",
                "current_number": user.updown_current_number,
                "round": user.updown_round,
                "multiplier": user.updown_multiplier,
                "bet": user.updown_bet
            }

        is_valid, bet_error = validate_bet(bet, user.cash)
        if not is_valid:
            return error_response(ErrorCode.INVALID_BET, bet_error)

        # 투자금 차감
        user.cash = safe_subtract(user.cash, bet)

        # 첫 숫자 생성 (극단값 회피: 5~95)
        first_number = random.randint(5, 95)

        # 게임 상태 저장
        user.updown_active = 1
        user.updown_bet = bet
        user.updown_current_number = first_number
        user.updown_round = 1
        user.updown_multiplier = 1.0

        try:
            db.commit()
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"업다운 시작 DB 커밋 실패: {e}")
            return error_response(ErrorCode.DB_ERROR, "데이터베이스 오류가 발생했습니다.")

        # 다음 라운드 배율 미리 계산 (라운드 수수료 반영)
        up_mult, down_mult, up_count, down_count = cls._preview_multipliers(first_number, 1)

        log_game(
            kakao_id=kakao_id, game_type="UPDOWN_START",
            bet=bet, result=f"number={first_number}",
            winnings=0, profit=0, cash_after=user.cash,
            extra=f"first_number={first_number}"
        )

        return {
            "success": True,
            "started": True,
            "number": first_number,
            "round": 1,
            "multiplier": 1.0,
            "bet": bet,
            "cash": user.cash,
            "up_multiplier": up_mult,
            "down_multiplier": down_mult,
            "can_up": up_count > 0,
            "can_down": down_count > 0,
        }

    @classmethod
    def play_updown_round(cls, db: Session, kakao_id: str, choice: str) -> Dict:
        """
        업다운 라운드 진행
        - 현재 숫자 대비 다음 숫자가 높은지(상승) 낮은지(하락) 예측
        - 맞추면 배율 누적, 계속 진행
        - 틀리면 투자금 전액 손실
        """
        user, error = get_user_with_error_for_update(db, kakao_id)
        if error:
            return error

        if not user.updown_active:
            return error_response(ErrorCode.INVALID_STATE, "진행 중인 업다운 게임이 없어요. /업다운 [금액] 으로 시작하세요!")

        choice_normalized = cls._normalize_updown_choice(choice)
        if not choice_normalized:
            return error_response(ErrorCode.INVALID_CHOICE, "상승/하락 중 선택해주세요.")

        current = user.updown_current_number

        # 방향 유효성 검증
        up_count = 100 - current
        down_count = current - 1

        if choice_normalized == "상승" and up_count == 0:
            return error_response(ErrorCode.INVALID_CHOICE, "현재 숫자가 100이라 상승을 선택할 수 없어요!")
        if choice_normalized == "하락" and down_count == 0:
            return error_response(ErrorCode.INVALID_CHOICE, "현재 숫자가 1이라 하락을 선택할 수 없어요!")

        # 다음 숫자 생성 (현재 숫자 제외)
        possible = [n for n in range(1, 101) if n != current]
        next_number = random.choice(possible)

        # 결과 판정
        if next_number > current:
            actual = "상승"
        else:
            actual = "하락"

        won = (choice_normalized == actual)

        # 이번 라운드 배율 계산 (공정: 1/확률)
        total = up_count + down_count
        if choice_normalized == "상승":
            prob = up_count / total
        else:
            prob = down_count / total
        raw_multiplier = 1 / prob

        # 라운드 수수료 적용 (정보 우위 상쇄)
        current_round = user.updown_round
        fee_rate = cls._round_fee_rate(current_round)
        round_multiplier = round(raw_multiplier * fee_rate, 2)

        if won:
            # 누적 배율 업데이트
            new_multiplier = round(user.updown_multiplier * round_multiplier, 2)
            user.updown_current_number = next_number
            user.updown_round += 1
            user.updown_multiplier = new_multiplier

            # 다음 라운드 배율 미리 계산 (다음 라운드 수수료 반영 — 표시와 실제 지급 일치)
            next_up_mult, next_down_mult, next_up_count, next_down_count = \
                cls._preview_multipliers(next_number, user.updown_round)

            try:
                db.commit()
            except SQLAlchemyError as e:
                db.rollback()
                logger.error(f"업다운 라운드 DB 커밋 실패: {e}")
                return error_response(ErrorCode.DB_ERROR, "데이터베이스 오류가 발생했습니다.")

            potential_winnings = safe_multiply(user.updown_bet, new_multiplier)

            log_game(
                kakao_id=kakao_id, game_type="UPDOWN_ROUND",
                bet=user.updown_bet, result=f"WIN round={user.updown_round}",
                winnings=0, profit=0, cash_after=user.cash,
                extra=f"prev={current} next={next_number} choice={choice_normalized} mult=x{round_multiplier} total=x{new_multiplier}"
            )

            return {
                "success": True,
                "won": True,
                "prev_number": current,
                "next_number": next_number,
                "choice": choice_normalized,
                "actual": actual,
                "round_multiplier": round_multiplier,
                "total_multiplier": new_multiplier,
                "round": user.updown_round,
                "bet": user.updown_bet,
                "potential_winnings": potential_winnings,
                "cash": user.cash,
                "up_multiplier": next_up_mult,
                "down_multiplier": next_down_mult,
                "can_up": next_up_count > 0,
                "can_down": next_down_count > 0,
            }
        else:
            # 실패 - 게임 종료, 투자금 손실
            bet = user.updown_bet
            user.updown_active = 0
            user.updown_bet = 0
            user.updown_current_number = 0
            user.updown_round = 0
            user.updown_multiplier = 1.0

            try:
                db.commit()
            except SQLAlchemyError as e:
                db.rollback()
                logger.error(f"업다운 실패 DB 커밋 실패: {e}")
                return error_response(ErrorCode.DB_ERROR, "데이터베이스 오류가 발생했습니다.")

            log_game(
                kakao_id=kakao_id, game_type="UPDOWN_LOSE",
                bet=bet, result="LOSE",
                winnings=0, profit=-bet, cash_after=user.cash,
                extra=f"prev={current} next={next_number} choice={choice_normalized} actual={actual}"
            )

            return {
                "success": True,
                "won": False,
                "prev_number": current,
                "next_number": next_number,
                "choice": choice_normalized,
                "actual": actual,
                "round_multiplier": round_multiplier,
                "bet": bet,
                "profit": -bet,
                "cash": user.cash,
            }

    @classmethod
    def cashout_updown(cls, db: Session, kakao_id: str) -> Dict:
        """업다운 중간 정산 — 현재 배율로 수익 확정"""
        user, error = get_user_with_error_for_update(db, kakao_id)
        if error:
            return error

        if not user.updown_active:
            return error_response(ErrorCode.INVALID_STATE, "진행 중인 업다운 게임이 없어요.")

        if user.updown_round < 2:
            return error_response(
                ErrorCode.INVALID_STATE,
                "최소 1라운드는 맞춰야 정산할 수 있어요!\n먼저 상승/하락을 선택해주세요."
            )

        bet = user.updown_bet
        multiplier = user.updown_multiplier
        winnings = safe_multiply(bet, multiplier)

        # 수익 지급
        user.cash = safe_add(user.cash, winnings)

        # 게임 상태 초기화
        final_round = user.updown_round
        user.updown_active = 0
        user.updown_bet = 0
        user.updown_current_number = 0
        user.updown_round = 0
        user.updown_multiplier = 1.0

        try:
            db.commit()
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"업다운 정산 DB 커밋 실패: {e}")
            return error_response(ErrorCode.DB_ERROR, "데이터베이스 오류가 발생했습니다.")

        profit = winnings - bet

        log_game(
            kakao_id=kakao_id, game_type="UPDOWN_CASHOUT",
            bet=bet, result=f"CASHOUT round={final_round} x{multiplier}",
            winnings=winnings, profit=profit, cash_after=user.cash,
            extra=f"multiplier=x{multiplier} rounds={final_round}"
        )

        return {
            "success": True,
            "bet": bet,
            "multiplier": multiplier,
            "winnings": winnings,
            "profit": profit,
            "rounds": final_round - 1,  # 맞춘 횟수 (시작 라운드 제외)
            "cash": user.cash,
        }

    @classmethod
    def get_updown_status(cls, db: Session, kakao_id: str) -> Dict:
        """업다운 게임 현재 상태 조회"""
        from services.common import get_user_with_error
        user, error = get_user_with_error(db, kakao_id)
        if error:
            return error

        if not user.updown_active:
            return {"success": True, "active": False}

        current = user.updown_current_number
        up_mult, down_mult, up_count, down_count = \
            cls._preview_multipliers(current, user.updown_round)

        return {
            "success": True,
            "active": True,
            "number": current,
            "round": user.updown_round,
            "multiplier": user.updown_multiplier,
            "bet": user.updown_bet,
            "potential_winnings": safe_multiply(user.updown_bet, user.updown_multiplier),
            "cash": user.cash,
            "up_multiplier": up_mult,
            "down_multiplier": down_mult,
            "can_up": up_count > 0,
            "can_down": down_count > 0,
        }

    @classmethod
    def _normalize_updown_choice(cls, choice: str) -> str:
        """업다운 선택 정규화"""
        choice = choice.lower().strip()
        if choice in ["상승", "상", "high", "높", "하이", "up"]:
            return "상승"
        elif choice in ["하락", "하", "low", "낮", "로우", "down"]:
            return "하락"
        return ""
