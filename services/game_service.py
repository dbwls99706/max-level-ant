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
from config import is_market_closed, get_market_status_message


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

    # 슬롯 확률 (기대값 90%, 고배율일수록 희귀)
    SLOT_PROBABILITIES = [
        ("7️⃣", 50, 0.0005),   # 0.05% - 잭팟 (매우 희귀)
        ("💎", 20, 0.0015),    # 0.15%
        ("🚀", 10, 0.003),     # 0.3%
        ("🍇", 5, 0.008),      # 0.8%
        ("🍊", 3, 0.02),       # 2%
        ("🍋", 2, 0.0575),     # 5.75%
        ("🍒", 1.5, 0.10),     # 10%
        ("MATCH2", 1, 0.45),   # 45% - 2개 일치 (본전)
        ("LOSE", 0, 0.3595),   # 35.95% - 꽝
    ]

    # 복권 1일 최대 횟수
    MAX_LOTTERY_PER_DAY = 5

    # 복권 가격
    LOTTERY_COST = 10_000

    @classmethod
    def play_lottery(cls, db: Session, kakao_id: str) -> Dict:
        """
        복권 긁기 (1일 5회, 1장 10,000원)
        - 일일 제한이 있으므로 장 시간 무관하게 가능
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

        # 잔액 확인
        if user.cash < cls.LOTTERY_COST:
            return {
                "success": False,
                "message": f"❌ 잔액 부족!\n복권 가격: {cls.LOTTERY_COST:,}원\n보유: {user.cash:,}원"
            }

        # 복권 구매 (비용 차감)
        user.cash -= cls.LOTTERY_COST

        # 복권 사용 기록
        user.lottery_count_today += 1
        remaining = cls.MAX_LOTTERY_PER_DAY - user.lottery_count_today

        # 복권 확률 (기준: 복권 1장 10,000원, 5회 수행 시 기대값 100%)
        roll = random.random()

        if roll < 0.0025:  # 0.25% - 1등 (50~100배)
            reward = random.randint(500_000, 1_000_000)
            tier = "🥇 1등"
            msg = "대박! 축하합니다!"
        elif roll < 0.025:  # 2.25% - 2등 (5~10배)
            reward = random.randint(50_000, 100_000)
            tier = "🥈 2등"
            msg = "좋아요!"
        elif roll < 0.09:  # 6.5% - 3등 (1.5~3배)
            reward = random.randint(15_000, 30_000)
            tier = "🥉 3등"
            msg = "괜찮네요!"
        elif roll < 0.23:  # 14% - 4등 (0.8~1.2배)
            reward = random.randint(8_000, 12_000)
            tier = "🎁 4등"
            msg = "조금이나마..."
        elif roll < 0.57:  # 34% - 5등 (본전 1배)
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
        profit = reward - cls.LOTTERY_COST

        return {
            "success": True,
            "cost": cls.LOTTERY_COST,
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
            status_msg = get_market_status_message()
            return {
                "success": False,
                "message": f"🎰 미니게임은 장 마감 후에만 가능해요!\n\n{status_msg}\n\n🎮 게임 가능 시간:\n• 평일 18:00 이후\n• 평일 08:30 이전\n• 주말/공휴일 종일"
            }

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
        - 빨강/검정: 2배
        - 초록(0): 14배
        """
        # 장 마감 시간에만 가능
        if not is_market_closed():
            status_msg = get_market_status_message()
            return {
                "success": False,
                "message": f"🎡 미니게임은 장 마감 후에만 가능해요!\n\n{status_msg}\n\n🎮 게임 가능 시간:\n• 평일 18:00 이후\n• 평일 08:30 이전\n• 주말/공휴일 종일"
            }

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
        # 장 마감 시간에만 가능
        if not is_market_closed():
            status_msg = get_market_status_message()
            return {
                "success": False,
                "message": f"🎲 미니게임은 장 마감 후에만 가능해요!\n\n{status_msg}\n\n🎮 게임 가능 시간:\n• 평일 18:00 이후\n• 평일 08:30 이전\n• 주말/공휴일 종일"
            }

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
        # 장 마감 시간에만 가능
        if not is_market_closed():
            status_msg = get_market_status_message()
            return {
                "success": False,
                "message": f"🪙 미니게임은 장 마감 후에만 가능해요!\n\n{status_msg}\n\n🎮 게임 가능 시간:\n• 평일 18:00 이후\n• 평일 08:30 이전\n• 주말/공휴일 종일"
            }

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
