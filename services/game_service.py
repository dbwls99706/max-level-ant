"""
미니게임 서비스
- 복권, 룰렛, 슬롯, 주가예측
- 24시간 플레이 가능
"""
import random
from datetime import date, datetime
from typing import Dict, Tuple, Optional
from sqlalchemy.orm import Session

from models import User


class GameService:
    """미니게임 서비스"""

    # 슬롯머신 심볼
    SLOT_SYMBOLS = ["🍒", "🍋", "🍊", "🍇", "💎", "7️⃣", "🚀"]

    # 슬롯 배당률 (매우 낮은 배당 - 잭팟 희귀)
    SLOT_PAYOUTS = {
        "7️⃣7️⃣7️⃣": 50,      # 잭팟 50배 (희귀 - 1/343 = 0.29%)
        "💎💎💎": 20,         # 다이아 20배
        "🚀🚀🚀": 10,         # 로켓 10배
        "🍇🍇🍇": 5,          # 포도 5배
        "🍊🍊🍊": 3,          # 오렌지 3배
        "🍋🍋🍋": 2,          # 레몬 2배
        "🍒🍒🍒": 1.5,        # 체리 1.5배
    }

    # 복권 1일 최대 횟수
    MAX_LOTTERY_PER_DAY = 3

    @classmethod
    def play_lottery(cls, db: Session, kakao_id: str) -> Dict:
        """
        복권 긁기 (1일 3회 무료)
        Returns: {"success": bool, "reward": int, "message": str}
        """
        user = db.query(User).filter(User.kakao_id == kakao_id).first()
        if not user:
            return {"success": False, "message": "먼저 /시작 으로 게임을 시작해주세요."}

        # 날짜가 바뀌었으면 카운트 리셋
        today = date.today()
        if user.last_lottery_date != today:
            user.last_lottery_date = today
            user.lottery_count_today = 0

        # 오늘 최대 횟수 체크
        if user.lottery_count_today >= cls.MAX_LOTTERY_PER_DAY:
            return {
                "success": False,
                "message": f"🎫 오늘 복권은 모두 긁었어요! ({cls.MAX_LOTTERY_PER_DAY}회)\n내일 다시 도전하세요 🍀"
            }

        # 복권 사용 기록
        user.lottery_count_today += 1
        remaining = cls.MAX_LOTTERY_PER_DAY - user.lottery_count_today

        # 복권 확률 (현실적 - 잭팟은 극히 희귀, 본전 확률 높게)
        roll = random.random()

        if roll < 0.0005:  # 0.05% - 대박 (극히 희귀)
            reward = random.randint(10_000_000, 20_000_000)
            tier = "🎊 대박"
            msg = "축하합니다!!! 전설의 대박!!!"
        elif roll < 0.005:  # 0.45% - 1등
            reward = random.randint(2_000_000, 5_000_000)
            tier = "🥇 1등"
            msg = "대단해요!"
        elif roll < 0.025:  # 2% - 2등
            reward = random.randint(500_000, 1_000_000)
            tier = "🥈 2등"
            msg = "좋아요!"
        elif roll < 0.075:  # 5% - 3등
            reward = random.randint(100_000, 300_000)
            tier = "🥉 3등"
            msg = "괜찮네요!"
        elif roll < 0.20:  # 12.5% - 4등
            reward = random.randint(20_000, 80_000)
            tier = "🎁 4등"
            msg = "조금이나마..."
        elif roll < 0.45:  # 25% - 5등 (본전)
            reward = random.randint(5_000, 15_000)
            tier = "💫 5등"
            msg = "본전이라도..."
        else:  # 55% - 꽝
            reward = random.randint(100, 2_000)
            tier = "😅 꽝"
            msg = "다음 기회에..."

        user.cash += reward
        db.commit()

        return {
            "success": True,
            "reward": reward,
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
        user = db.query(User).filter(User.kakao_id == kakao_id).first()
        if not user:
            return {"success": False, "message": "먼저 /시작 으로 게임을 시작해주세요."}

        if user.cash < bet:
            return {
                "success": False,
                "message": f"잔액 부족! (보유: {user.cash:,}원, 필요: {bet:,}원)"
            }

        # 배팅금 차감
        user.cash -= bet

        # 슬롯 돌리기
        slot1 = random.choice(cls.SLOT_SYMBOLS)
        slot2 = random.choice(cls.SLOT_SYMBOLS)
        slot3 = random.choice(cls.SLOT_SYMBOLS)

        result = f"{slot1}{slot2}{slot3}"

        # 당첨 확인
        multiplier = 0
        if result in cls.SLOT_PAYOUTS:
            multiplier = cls.SLOT_PAYOUTS[result]
        elif slot1 == slot2 or slot2 == slot3 or slot1 == slot3:
            # 2개 일치 - 1배 (본전)
            multiplier = 1.0

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
        - 빨강/검정: 2배
        - 초록(0): 14배
        """
        user = db.query(User).filter(User.kakao_id == kakao_id).first()
        if not user:
            return {"success": False, "message": "먼저 /시작 으로 게임을 시작해주세요."}

        min_bet = 10_000
        if bet < min_bet:
            return {"success": False, "message": f"최소 배팅금은 {min_bet:,}원입니다."}

        if user.cash < bet:
            return {
                "success": False,
                "message": f"잔액 부족! (보유: {user.cash:,}원)"
            }

        choice = choice.lower()
        if choice not in ["빨강", "검정", "초록", "red", "black", "green"]:
            return {"success": False, "message": "빨강, 검정, 초록 중 선택해주세요."}

        # 정규화
        if choice in ["red", "빨강"]:
            choice = "빨강"
        elif choice in ["black", "검정"]:
            choice = "검정"
        else:
            choice = "초록"

        # 배팅금 차감
        user.cash -= bet

        # 룰렛 돌리기 (0-36)
        number = random.randint(0, 36)

        if number == 0:
            result = "초록"
            emoji = "🟢"
        elif number % 2 == 0:
            result = "빨강"
            emoji = "🔴"
        else:
            result = "검정"
            emoji = "⚫"

        # 당첨 확인
        won = (choice == result)

        if won:
            if result == "초록":
                multiplier = 14
            else:
                multiplier = 2
            winnings = bet * multiplier
        else:
            multiplier = 0
            winnings = 0

        user.cash += winnings
        db.commit()

        return {
            "success": True,
            "number": number,
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
        - 맞추면 1.9배
        """
        user = db.query(User).filter(User.kakao_id == kakao_id).first()
        if not user:
            return {"success": False, "message": "먼저 /시작 으로 게임을 시작해주세요."}

        min_bet = 10_000
        if bet < min_bet:
            return {"success": False, "message": f"최소 배팅금은 {min_bet:,}원입니다."}

        if user.cash < bet:
            return {
                "success": False,
                "message": f"잔액 부족! (보유: {user.cash:,}원)"
            }

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
            multiplier = 1.9
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
        - 앞/뒤 맞추면 1.95배
        """
        user = db.query(User).filter(User.kakao_id == kakao_id).first()
        if not user:
            return {"success": False, "message": "먼저 /시작 으로 게임을 시작해주세요."}

        min_bet = 10_000
        if bet < min_bet:
            return {"success": False, "message": f"최소 배팅금은 {min_bet:,}원입니다."}

        if user.cash < bet:
            return {
                "success": False,
                "message": f"잔액 부족! (보유: {user.cash:,}원)"
            }

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
            multiplier = 1.95
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
