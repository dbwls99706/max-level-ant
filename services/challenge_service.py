"""
주간 챌린지 서비스
"""
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
import random
from sqlalchemy.orm import Session

from models import WeeklyChallenge, UserChallenge, User


class ChallengeService:
    """주간 챌린지 서비스"""

    # 챌린지 타입 정의
    CHALLENGE_TYPES = {
        "TRADE_COUNT": {
            "name": "거래왕",
            "description": "이번 주 {target}회 거래하기",
            "targets": [5, 10, 15, 20],
            "rewards": [1_000_000, 2_000_000, 3_000_000, 5_000_000]
        },
        "PROFIT_RATE": {
            "name": "수익 챔피언",
            "description": "이번 주 수익률 {target}% 달성",
            "targets": [5, 10, 20, 30],
            "rewards": [2_000_000, 3_000_000, 5_000_000, 10_000_000]
        },
        "ATTENDANCE": {
            "name": "개근왕",
            "description": "이번 주 {target}일 출석하기",
            "targets": [3, 5, 7],
            "rewards": [500_000, 1_500_000, 3_000_000]
        },
        "LOTTERY": {
            "name": "행운의 주인공",
            "description": "복권 {target}회 당첨되기 (꽝 제외)",
            "targets": [3, 5, 10],
            "rewards": [500_000, 1_000_000, 2_000_000]
        },
        "ASSET_GROWTH": {
            "name": "자산 성장",
            "description": "총 자산 {target}만원 증가",
            "targets": [100, 300, 500, 1000],
            "rewards": [1_000_000, 2_000_000, 4_000_000, 8_000_000]
        }
    }

    @classmethod
    def get_current_week_id(cls) -> str:
        """현재 주차 ID 반환 (예: 2024-W01)"""
        today = date.today()
        return today.strftime("%Y-W%W")

    @classmethod
    def get_or_create_weekly_challenge(cls, db: Session) -> Optional[WeeklyChallenge]:
        """현재 주차 챌린지 가져오기 (없으면 생성)"""
        week_id = cls.get_current_week_id()

        # 기존 챌린지 확인
        challenge = db.query(WeeklyChallenge).filter(
            WeeklyChallenge.week_id == week_id
        ).first()

        if challenge:
            return challenge

        # 새 챌린지 생성
        today = date.today()
        # 이번 주 월요일
        monday = today - timedelta(days=today.weekday())
        # 이번 주 일요일
        sunday = monday + timedelta(days=6)

        # 랜덤 챌린지 타입 선택
        challenge_type = random.choice(list(cls.CHALLENGE_TYPES.keys()))
        type_info = cls.CHALLENGE_TYPES[challenge_type]

        # 랜덤 난이도 선택
        difficulty = random.randint(0, len(type_info["targets"]) - 1)
        target = type_info["targets"][difficulty]
        reward = type_info["rewards"][difficulty]

        description = type_info["description"].format(target=target)

        challenge = WeeklyChallenge(
            week_id=week_id,
            challenge_type=challenge_type,
            target_value=target,
            description=f"🎯 {type_info['name']}: {description}",
            reward=reward,
            start_date=monday,
            end_date=sunday
        )

        db.add(challenge)
        db.commit()
        db.refresh(challenge)

        return challenge

    @classmethod
    def get_user_challenge_progress(cls, db: Session, kakao_id: str) -> Dict:
        """유저의 현재 챌린지 진행상황"""
        challenge = cls.get_or_create_weekly_challenge(db)
        if not challenge:
            return {"success": False, "message": "챌린지 정보를 가져올 수 없습니다."}

        # 유저 챌린지 기록 가져오기
        user_challenge = db.query(UserChallenge).filter(
            UserChallenge.kakao_id == kakao_id,
            UserChallenge.challenge_id == challenge.id
        ).first()

        if not user_challenge:
            # 새 기록 생성
            user_challenge = UserChallenge(
                kakao_id=kakao_id,
                challenge_id=challenge.id,
                current_value=0,
                completed=0,
                reward_claimed=0
            )
            db.add(user_challenge)
            db.commit()
            db.refresh(user_challenge)

        progress_rate = min((user_challenge.current_value / challenge.target_value) * 100, 100)

        return {
            "success": True,
            "challenge": {
                "id": challenge.id,
                "week_id": challenge.week_id,
                "type": challenge.challenge_type,
                "description": challenge.description,
                "target": challenge.target_value,
                "reward": challenge.reward,
                "start_date": str(challenge.start_date),
                "end_date": str(challenge.end_date)
            },
            "progress": {
                "current": user_challenge.current_value,
                "target": challenge.target_value,
                "progress_rate": progress_rate,
                "completed": user_challenge.completed == 1,
                "reward_claimed": user_challenge.reward_claimed == 1
            }
        }

    @classmethod
    def update_challenge_progress(
        cls,
        db: Session,
        kakao_id: str,
        challenge_type: str,
        increment: int = 1
    ) -> Optional[Dict]:
        """
        챌린지 진행도 업데이트
        거래 완료, 출석 완료 등 이벤트 발생 시 호출
        """
        challenge = cls.get_or_create_weekly_challenge(db)
        if not challenge or challenge.challenge_type != challenge_type:
            return None

        user_challenge = db.query(UserChallenge).filter(
            UserChallenge.kakao_id == kakao_id,
            UserChallenge.challenge_id == challenge.id
        ).first()

        if not user_challenge:
            user_challenge = UserChallenge(
                kakao_id=kakao_id,
                challenge_id=challenge.id,
                current_value=0
            )
            db.add(user_challenge)

        # 이미 완료된 경우 스킵
        if user_challenge.completed == 1:
            return None

        user_challenge.current_value += increment

        # 목표 달성 체크
        if user_challenge.current_value >= challenge.target_value:
            user_challenge.completed = 1
            db.commit()
            return {
                "completed": True,
                "challenge_name": challenge.description,
                "reward": challenge.reward
            }

        db.commit()
        return None

    @classmethod
    def claim_challenge_reward(cls, db: Session, kakao_id: str) -> Dict:
        """챌린지 보상 수령"""
        challenge = cls.get_or_create_weekly_challenge(db)
        if not challenge:
            return {"success": False, "message": "챌린지 정보를 가져올 수 없습니다."}

        user_challenge = db.query(UserChallenge).filter(
            UserChallenge.kakao_id == kakao_id,
            UserChallenge.challenge_id == challenge.id
        ).first()

        if not user_challenge:
            return {"success": False, "message": "챌린지에 참가하지 않았습니다."}

        if user_challenge.completed != 1:
            return {"success": False, "message": "아직 챌린지를 완료하지 않았습니다."}

        if user_challenge.reward_claimed == 1:
            return {"success": False, "message": "이미 보상을 수령했습니다."}

        # 보상 지급
        user = db.query(User).filter(User.kakao_id == kakao_id).first()
        user.cash += challenge.reward
        user_challenge.reward_claimed = 1

        db.commit()

        return {
            "success": True,
            "reward": challenge.reward,
            "cash": user.cash,
            "message": f"🎉 챌린지 보상 {challenge.reward:,}원 지급!"
        }
