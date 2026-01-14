"""
미니게임 서비스
- 복권, 슬롯, 동전, 하이로우
- 장 마감 시간에만 플레이 가능 (18:00 이후, 08:30 이전, 주말, 공휴일)
"""
import random
from datetime import date, datetime
from typing import Dict, Tuple, Optional
from sqlalchemy.orm import Session

from models import User
from config import is_market_closed, get_market_status_message, GameConfig, Messages


def _validate_bet(user, bet: int) -> Optional[Dict]:
    """배팅금 검증 (공통 함수). 문제 있으면 에러 dict 반환, 없으면 None"""
    if bet <= 0:
        return {"success": False, "message": Messages.BET_ZERO_OR_NEGATIVE}
    if bet < GameConfig.MIN_BET:
        return {"success": False, "message": Messages.BET_TOO_SMALL.format(min_bet=GameConfig.MIN_BET)}
    if bet > GameConfig.MAX_BET:
        return {"success": False, "message": Messages.BET_TOO_LARGE.format(max_bet=GameConfig.MAX_BET)}
    if user.cash < bet:
        return {"success": False, "message": f"❌ 잔액 부족! (보유: {user.cash:,}원, 필요: {bet:,}원)"}
    return None


def _get_market_closed_error(emoji: str) -> Dict:
    """장 마감 시간 에러 메시지 (중복 제거)"""
    status_msg = get_market_status_message()
    return {
        "success": False,
        "message": f"{emoji} " + Messages.MARKET_CLOSED_GAME.format(status_msg=status_msg)
    }


class GameService:
    """미니게임 서비스"""

    # 슬롯머신 심볼
    SLOT_SYMBOLS = ["🍒", "🍋", "🍊", "🍇", "💎", "7️⃣", "🚀"]

    # 슬롯 배당률 (원래 배수 유지)
    SLOT_PAYOUTS = {
        "7️⃣7️⃣7️⃣": 50,      # 잭팟 50배
        "💎💎💎": 20,         # 다이아 20배
        "🚀🚀🚀": 10,         # 로켓 10배
        "🍇🍇🍇": 5,          # 포도 5배
        "🍊🍊🍊": 3,          # 오렌지 3배
        "🍋🍋🍋": 2,          # 레몬 2배
        "🍒🍒🍒": 1.5,        # 체리 1.5배
    }

    # 슬롯 확률 (잭팟/다이아/로켓은 희귀하게 유지)
    SLOT_PROBABILITIES = [
        ("7️⃣", 50, 0.0005),   # 0.05% - 잭팟 (희귀)
        ("💎", 20, 0.0015),    # 0.15% (희귀)
        ("🚀", 10, 0.003),     # 0.3% (희귀)
        ("🍇", 5, 0.012),      # 1.2%
        ("🍊", 3, 0.025),      # 2.5%
        ("🍋", 2, 0.0575),     # 5.75%
        ("🍒", 1.5, 0.10),     # 10%
        ("MATCH2", 1, 0.35),   # 35% - 2개 일치 (본전)
        ("LOSE", 0, 0.4505),   # 45.05% - 꽝
    ]

    @classmethod
    def play_lottery(cls, db: Session, kakao_id: str) -> Dict:
        """
        복권 긁기 (1일 5회, 1장 10,000원)
        - 일일 제한이 있으므로 장 시간 무관하게 가능
        Returns: {"success": bool, "reward": int, "message": str}
        """
        user = db.query(User).filter(User.kakao_id == kakao_id).first()
        if not user:
            return {"success": False, "message": Messages.USER_NOT_FOUND}

        # 날짜가 바뀌었으면 카운트 리셋
        today = date.today()
        if user.last_lottery_date != today:
            user.last_lottery_date = today
            user.lottery_count_today = 0

        # 오늘 최대 횟수 체크
        if user.lottery_count_today >= GameConfig.MAX_LOTTERY_PER_DAY:
            return {
                "success": False,
                "message": f"🎫 오늘 복권은 모두 긁었어요! ({GameConfig.MAX_LOTTERY_PER_DAY}회)\n내일 다시 도전하세요 🍀"
            }

        # 잔액 확인
        if user.cash < GameConfig.LOTTERY_COST:
            return {
                "success": False,
                "message": f"❌ 잔액 부족!\n복권 가격: {GameConfig.LOTTERY_COST:,}원\n보유: {user.cash:,}원"
            }

        # 복권 구매 (비용 차감)
        user.cash -= GameConfig.LOTTERY_COST

        # 복권 사용 기록
        user.lottery_count_today += 1
        remaining = GameConfig.MAX_LOTTERY_PER_DAY - user.lottery_count_today

        # 복권 확률 (기준: 복권 1장 10,000원, 기대값 90%)
        roll = random.random()

        if roll < 0.002:  # 0.2% - 1등 (50~100배)
            reward = random.randint(500_000, 1_000_000)
            tier = "🥇 1등"
            msg = "대박! 축하합니다!"
        elif roll < 0.02:  # 1.8% - 2등 (5~10배)
            reward = random.randint(50_000, 100_000)
            tier = "🥈 2등"
            msg = "좋아요!"
        elif roll < 0.07:  # 5% - 3등 (1.5~3배)
            reward = random.randint(15_000, 30_000)
            tier = "🥉 3등"
            msg = "괜찮네요!"
        elif roll < 0.17:  # 10% - 4등 (0.8~1.2배)
            reward = random.randint(8_000, 12_000)
            tier = "🎁 4등"
            msg = "조금이나마..."
        elif roll < 0.47:  # 30% - 5등 (본전 1배)
            reward = 10_000
            tier = "💫 5등"
            msg = "본전!"
        else:  # 43% - 꽝
            reward = random.randint(0, 1_000)
            tier = "😅 꽝"
            msg = "다음 기회에..."

        user.cash += reward
        db.commit()

        # 순이익 계산
        profit = reward - GameConfig.LOTTERY_COST

        return {
            "success": True,
            "cost": GameConfig.LOTTERY_COST,
            "reward": reward,
            "profit": profit,
            "tier": tier,
            "message": msg,
            "cash": user.cash,
            "remaining": remaining
        }

    @classmethod
    def play_slot(cls, db: Session, kakao_id: str, bet: int = 50_000) -> Dict:
        """
        슬롯머신 (배팅 금액 필요)
        """
        # 장 마감 시간에만 가능
        if not is_market_closed():
            return _get_market_closed_error("🎰")

        user = db.query(User).filter(User.kakao_id == kakao_id).first()
        if not user:
            return {"success": False, "message": Messages.USER_NOT_FOUND}

        # 배팅금 검증
        bet_error = _validate_bet(user, bet)
        if bet_error:
            return bet_error

        # 배팅금 차감
        user.cash -= bet

        # 확률 기반 결과 결정
        roll = random.random()
        cumulative = 0
        outcome_symbol = None
        multiplier = 0

        for symbol, mult, prob in cls.SLOT_PROBABILITIES:
            cumulative += prob
            if roll < cumulative:
                outcome_symbol = symbol
                multiplier = mult
                break

        # 슬롯 심볼 생성
        if outcome_symbol == "LOSE":
            # 꽝: 모두 다른 심볼
            symbols = random.sample(cls.SLOT_SYMBOLS, 3)
            slot1, slot2, slot3 = symbols
        elif outcome_symbol == "MATCH2":
            # 2개 일치 (본전)
            match_symbol = random.choice(cls.SLOT_SYMBOLS)
            other_symbols = [s for s in cls.SLOT_SYMBOLS if s != match_symbol]
            other = random.choice(other_symbols)
            pattern = random.choice([
                [match_symbol, match_symbol, other],
                [match_symbol, other, match_symbol],
                [other, match_symbol, match_symbol]
            ])
            slot1, slot2, slot3 = pattern
        else:
            # 3개 일치
            slot1 = slot2 = slot3 = outcome_symbol

        result = f"{slot1}{slot2}{slot3}"

        winnings = int(bet * multiplier)
        user.cash += winnings
        db.commit()

        profit = winnings - bet

        return {
            "success": True,
            "slots": [slot1, slot2, slot3],
            "result": result,
            "bet": bet,
            "multiplier": multiplier,
            "winnings": winnings,
            "profit": profit,
            "cash": user.cash,
            "jackpot": multiplier >= 20
        }

    @classmethod
    def play_roulette(cls, db: Session, kakao_id: str, bet: int, choice: str) -> Dict:
        """
        룰렛 (빨강/검정/초록)
        - 빨강/검정: 2배 (45% 확률)
        - 초록: 9배 (10% 확률)
        - 기대값 90%
        """
        # 장 마감 시간에만 가능
        if not is_market_closed():
            return _get_market_closed_error("🎡")

        user = db.query(User).filter(User.kakao_id == kakao_id).first()
        if not user:
            return {"success": False, "message": Messages.USER_NOT_FOUND}

        # 배팅금 검증
        bet_error = _validate_bet(user, bet)
        if bet_error:
            return bet_error

        choice = choice.lower()
        if choice not in ["빨강", "검정", "초록", "red", "black", "green", "빨", "검", "초"]:
            return {"success": False, "message": "빨강, 검정, 초록 중 선택해주세요."}

        # 정규화
        if choice in ["red", "빨강", "빨"]:
            choice = "빨강"
        elif choice in ["black", "검정", "검"]:
            choice = "검정"
        else:
            choice = "초록"

        # 배팅금 차감
        user.cash -= bet

        # 룰렛 결과 (기대값 90%: 빨강 45%, 검정 45%, 초록 10%)
        roll = random.random()
        if roll < 0.45:
            result = "빨강"
            emoji = "🔴"
        elif roll < 0.90:
            result = "검정"
            emoji = "⚫"
        else:
            result = "초록"
            emoji = "🟢"

        # 당첨 확인
        won = (choice == result)

        if won:
            if result == "초록":
                multiplier = 9  # 10% × 9 = 90% EV
            else:
                multiplier = 2  # 45% × 2 = 90% EV
            winnings = bet * multiplier
        else:
            multiplier = 0
            winnings = 0

        user.cash += winnings
        db.commit()

        return {
            "success": True,
            "result": result,
            "emoji": emoji,
            "choice": choice,
            "won": won,
            "bet": bet,
            "multiplier": multiplier,
            "winnings": winnings,
            "profit": winnings - bet,
            "cash": user.cash
        }

    @classmethod
    def play_high_low(cls, db: Session, kakao_id: str, bet: int, choice: str) -> Dict:
        """
        하이로우 게임
        - 1-100 숫자 중 50보다 높은지 낮은지
        - 맞추면 1.8배 (기대값 90%)
        """
        # 장 마감 시간에만 가능
        if not is_market_closed():
            return _get_market_closed_error("🎲")

        user = db.query(User).filter(User.kakao_id == kakao_id).first()
        if not user:
            return {"success": False, "message": Messages.USER_NOT_FOUND}

        # 배팅금 검증
        bet_error = _validate_bet(user, bet)
        if bet_error:
            return bet_error

        choice = choice.lower()
        if choice not in ["높", "낮", "high", "low", "하이", "로우"]:
            return {"success": False, "message": "높/낮 중 선택해주세요."}

        # 정규화
        if choice in ["high", "높", "하이"]:
            choice = "높"
        else:
            choice = "낮"

        # 배팅금 차감
        user.cash -= bet

        # 숫자 뽑기 (1-100, 50은 무승부)
        number = random.randint(1, 100)

        if number == 50:
            # 무승부 - 배팅금 반환
            user.cash += bet
            db.commit()
            return {
                "success": True,
                "number": number,
                "choice": choice,
                "won": None,  # 무승부
                "bet": bet,
                "winnings": bet,
                "profit": 0,
                "cash": user.cash,
                "message": "무승부! 배팅금 반환"
            }

        actual = "높" if number > 50 else "낮"
        won = (choice == actual)

        if won:
            multiplier = 1.8  # 50% × 1.8 = 90% EV
            winnings = int(bet * multiplier)
        else:
            multiplier = 0
            winnings = 0

        user.cash += winnings
        db.commit()

        return {
            "success": True,
            "number": number,
            "actual": actual,
            "choice": choice,
            "won": won,
            "bet": bet,
            "multiplier": multiplier if won else 0,
            "winnings": winnings,
            "profit": winnings - bet,
            "cash": user.cash
        }

    @classmethod
    def play_coin_flip(cls, db: Session, kakao_id: str, bet: int, choice: str) -> Dict:
        """
        동전 던지기
        - 앞/뒤 맞추면 2배 (기대값 100%)
        """
        # 장 마감 시간에만 가능
        if not is_market_closed():
            return _get_market_closed_error("🪙")

        user = db.query(User).filter(User.kakao_id == kakao_id).first()
        if not user:
            return {"success": False, "message": Messages.USER_NOT_FOUND}

        # 배팅금 검증
        bet_error = _validate_bet(user, bet)
        if bet_error:
            return bet_error

        choice = choice.lower()
        if choice not in ["앞", "뒤", "head", "tail", "앞면", "뒷면"]:
            return {"success": False, "message": "앞/뒤 중 선택해주세요."}

        # 정규화
        if choice in ["head", "앞", "앞면"]:
            choice = "앞"
        else:
            choice = "뒤"

        # 배팅금 차감
        user.cash -= bet

        # 동전 던지기
        result = random.choice(["앞", "뒤"])
        emoji = "🪙" if result == "앞" else "💿"

        won = (choice == result)

        if won:
            multiplier = 2.0  # 50% × 2.0 = 100% EV
            winnings = int(bet * multiplier)
        else:
            multiplier = 0
            winnings = 0

        user.cash += winnings
        db.commit()

        return {
            "success": True,
            "result": result,
            "emoji": emoji,
            "choice": choice,
            "won": won,
            "bet": bet,
            "multiplier": multiplier if won else 0,
            "winnings": winnings,
            "profit": winnings - bet,
            "cash": user.cash
        }
