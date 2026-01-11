"""
미션 및 업적 서비스
- 일간 미션
- 업적 시스템
- 주간 보너스
"""
import json
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from models import User
from config import GameConfig


# 업적 정의
ACHIEVEMENTS = {
    "first_trade": {
        "id": "first_trade",
        "name": "첫 거래",
        "description": "첫 번째 주식 거래 완료",
        "reward": 500_000,
        "icon": "🎯"
    },
    "first_profit": {
        "id": "first_profit",
        "name": "첫 수익",
        "description": "처음으로 수익 실현",
        "reward": 1_000_000,
        "icon": "💰"
    },
    "profit_1m": {
        "id": "profit_1m",
        "name": "100만원 수익",
        "description": "누적 실현 수익 100만원 달성",
        "reward": 2_000_000,
        "icon": "📈"
    },
    "profit_10m": {
        "id": "profit_10m",
        "name": "1000만원 수익",
        "description": "누적 실현 수익 1000만원 달성",
        "reward": 5_000_000,
        "icon": "🚀"
    },
    "profit_100m": {
        "id": "profit_100m",
        "name": "1억 수익",
        "description": "누적 실현 수익 1억원 달성",
        "reward": 20_000_000,
        "icon": "👑"
    },
    "trades_10": {
        "id": "trades_10",
        "name": "거래 10회",
        "description": "총 10회 거래 달성",
        "reward": 500_000,
        "icon": "📊"
    },
    "trades_50": {
        "id": "trades_50",
        "name": "거래 50회",
        "description": "총 50회 거래 달성",
        "reward": 2_000_000,
        "icon": "📈"
    },
    "trades_100": {
        "id": "trades_100",
        "name": "거래 100회",
        "description": "총 100회 거래 달성",
        "reward": 5_000_000,
        "icon": "🏆"
    },
    "streak_7": {
        "id": "streak_7",
        "name": "7일 연속 출석",
        "description": "7일 연속 출석 달성",
        "reward": 3_000_000,
        "icon": "🔥"
    },
    "millionaire": {
        "id": "millionaire",
        "name": "억만장자",
        "description": "총 자산 1억원 달성",
        "reward": 10_000_000,
        "icon": "💎"
    }
}


class MissionService:
    """미션 및 업적 관련 서비스"""

    @staticmethod
    def check_daily_mission(db: Session, kakao_id: str) -> Dict:
        """
        일간 미션 상태 확인
        Returns: {"completed": bool, "progress": int, "target": int, "reward": int}
        """
        user = db.query(User).filter(User.kakao_id == kakao_id).first()
        if not user:
            return {"completed": False, "progress": 0, "target": 0, "reward": 0}

        today = date.today()

        # 날짜가 바뀌었으면 리셋
        if user.last_mission_date != today:
            user.last_mission_date = today
            user.daily_trade_count = 0
            user.mission_completed = 0
            db.commit()

        return {
            "completed": user.mission_completed == 1,
            "progress": user.daily_trade_count,
            "target": GameConfig.DAILY_MISSION_TRADE_COUNT,
            "reward": GameConfig.DAILY_MISSION_REWARD
        }

    @staticmethod
    def increment_trade_count(db: Session, kakao_id: str) -> Optional[Dict]:
        """
        거래 횟수 증가 및 미션 완료 체크
        Returns: 미션 완료 시 보상 정보, 아니면 None
        """
        user = db.query(User).filter(User.kakao_id == kakao_id).first()
        if not user:
            return None

        today = date.today()

        # 날짜가 바뀌었으면 리셋
        if user.last_mission_date != today:
            user.last_mission_date = today
            user.daily_trade_count = 0
            user.mission_completed = 0

        # 거래 횟수 증가
        user.daily_trade_count += 1
        user.total_trades += 1

        # 미션 완료 체크 (아직 미완료 상태일 때만)
        reward_info = None
        if (user.mission_completed == 0 and
                user.daily_trade_count >= GameConfig.DAILY_MISSION_TRADE_COUNT):
            user.mission_completed = 1

            # 주간 보너스 체크
            multiplier = 1.0
            if datetime.now().weekday() == GameConfig.WEEKLY_BONUS_DAY:
                multiplier = GameConfig.WEEKLY_BONUS_MULTIPLIER

            reward = int(GameConfig.DAILY_MISSION_REWARD * multiplier)
            user.cash += reward

            reward_info = {
                "reward": reward,
                "is_bonus_day": multiplier > 1.0,
                "multiplier": multiplier
            }

        db.commit()
        return reward_info

    @staticmethod
    def get_user_achievements(db: Session, kakao_id: str) -> List[Dict]:
        """
        유저의 달성한 업적 목록 조회
        """
        user = db.query(User).filter(User.kakao_id == kakao_id).first()
        if not user:
            return []

        try:
            achieved_ids = json.loads(user.achievements or "[]")
        except json.JSONDecodeError:
            achieved_ids = []

        result = []
        for ach_id in achieved_ids:
            if ach_id in ACHIEVEMENTS:
                result.append(ACHIEVEMENTS[ach_id])

        return result

    @staticmethod
    def get_available_achievements(db: Session, kakao_id: str) -> List[Dict]:
        """
        아직 달성하지 못한 업적 목록 조회
        """
        user = db.query(User).filter(User.kakao_id == kakao_id).first()
        if not user:
            return list(ACHIEVEMENTS.values())

        try:
            achieved_ids = json.loads(user.achievements or "[]")
        except json.JSONDecodeError:
            achieved_ids = []

        result = []
        for ach_id, ach in ACHIEVEMENTS.items():
            if ach_id not in achieved_ids:
                result.append(ach)

        return result

    @staticmethod
    def check_and_award_achievements(
            db: Session,
            kakao_id: str,
            trade_profit: int = 0
    ) -> List[Dict]:
        """
        업적 달성 체크 및 보상 지급
        Returns: 새로 달성한 업적 목록
        """
        user = db.query(User).filter(User.kakao_id == kakao_id).first()
        if not user:
            return []

        try:
            achieved_ids = json.loads(user.achievements or "[]")
        except json.JSONDecodeError:
            achieved_ids = []

        # 실현 수익 업데이트
        if trade_profit > 0:
            user.total_profit_realized += trade_profit

        new_achievements = []

        # 업적 체크
        checks = [
            ("first_trade", user.total_trades >= 1),
            ("first_profit", user.total_profit_realized > 0),
            ("profit_1m", user.total_profit_realized >= 1_000_000),
            ("profit_10m", user.total_profit_realized >= 10_000_000),
            ("profit_100m", user.total_profit_realized >= 100_000_000),
            ("trades_10", user.total_trades >= 10),
            ("trades_50", user.total_trades >= 50),
            ("trades_100", user.total_trades >= 100),
            ("streak_7", user.attendance_streak >= 7),
        ]

        for ach_id, condition in checks:
            if condition and ach_id not in achieved_ids:
                achieved_ids.append(ach_id)
                ach = ACHIEVEMENTS[ach_id]
                user.cash += ach["reward"]
                new_achievements.append(ach)

        # 저장
        user.achievements = json.dumps(achieved_ids)
        db.commit()

        return new_achievements

    @staticmethod
    def is_bonus_day() -> Tuple[bool, float]:
        """
        오늘이 주간 보너스 요일인지 확인
        Returns: (is_bonus_day, multiplier)
        """
        today_weekday = datetime.now().weekday()
        is_bonus = today_weekday == GameConfig.WEEKLY_BONUS_DAY
        multiplier = GameConfig.WEEKLY_BONUS_MULTIPLIER if is_bonus else 1.0
        return is_bonus, multiplier

    @staticmethod
    def get_mission_status(db: Session, kakao_id: str) -> Dict:
        """
        전체 미션/업적 현황 조회
        """
        user = db.query(User).filter(User.kakao_id == kakao_id).first()
        if not user:
            return {}

        mission = MissionService.check_daily_mission(db, kakao_id)
        achieved = MissionService.get_user_achievements(db, kakao_id)
        available = MissionService.get_available_achievements(db, kakao_id)
        is_bonus, multiplier = MissionService.is_bonus_day()

        return {
            "daily_mission": mission,
            "achievements_completed": len(achieved),
            "achievements_total": len(ACHIEVEMENTS),
            "achievements": achieved,
            "available_achievements": available,
            "is_bonus_day": is_bonus,
            "bonus_multiplier": multiplier,
            "total_trades": user.total_trades,
            "total_profit_realized": user.total_profit_realized
        }
