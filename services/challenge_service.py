"""
주간 챌린지 서비스 (리팩토링)
- 트랜잭션 안전성 강화
- 0 나누기 방지
"""
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
import random
from sqlalchemy.orm import Session

from models import WeeklyChallenge, UserChallenge, User
from services.common import (
    get_user_with_error,
    error_response,
    success_response,
    safe_add,
)
from config import ErrorCode
from utils import get_handler_logger

logger = get_handler_logger()


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

        try:
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
        except Exception as e:
            db.rollback()
            logger.error(f"주간 챌린지 생성 실패: {e}")
            return None

        return challenge

    @classmethod
    def get_user_challenge_progress(cls, db: Session, kakao_id: str) -> Dict:
        """유저의 현재 챌린지 진행상황"""
        challenge = cls.get_or_create_weekly_challenge(db)
        if not challenge:
            return error_response(
                ErrorCode.INTERNAL_ERROR,
                "챌린지 정보를 가져올 수 없습니다."
            )

        # 유저 챌린지 기록 가져오기
        user_challenge = db.query(UserChallenge).filter(
            UserChallenge.kakao_id == kakao_id,
            UserChallenge.challenge_id == challenge.id
        ).first()

        if not user_challenge:
            # 새 기록 생성
            try:
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
            except Exception as e:
                db.rollback()
                logger.error(f"유저 챌린지 기록 생성 실패: {e}")
                return error_response(
                    ErrorCode.INTERNAL_ERROR,
                    "챌린지 참가 등록에 실패했습니다."
                )

        # 진행률 계산 (0으로 나누기 방지)
        target = challenge.target_value if challenge.target_value > 0 else 1
        progress_rate = min((user_challenge.current_value / target) * 100, 100)

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
            try:
                user_challenge = UserChallenge(
                    kakao_id=kakao_id,
                    challenge_id=challenge.id,
                    current_value=0
                )
                db.add(user_challenge)
            except Exception as e:
                logger.error(f"유저 챌린지 생성 중 오류: {e}")
                return None

        # 이미 완료된 경우 스킵
        if user_challenge.completed == 1:
            return None

        try:
            user_challenge.current_value += increment

            # 목표 달성 체크 (0으로 나누기 방지)
            target = challenge.target_value if challenge.target_value > 0 else 1
            if user_challenge.current_value >= target:
                user_challenge.completed = 1
                db.commit()
                return {
                    "completed": True,
                    "challenge_name": challenge.description,
                    "reward": challenge.reward
                }

            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"챌린지 진행도 업데이트 실패: {e}")

        return None

    @classmethod
    def claim_challenge_reward(cls, db: Session, kakao_id: str) -> Dict:
        """챌린지 보상 수령"""
        challenge = cls.get_or_create_weekly_challenge(db)
        if not challenge:
            return error_response(
                ErrorCode.INTERNAL_ERROR,
                "챌린지 정보를 가져올 수 없습니다."
            )

        user_challenge = db.query(UserChallenge).filter(
            UserChallenge.kakao_id == kakao_id,
            UserChallenge.challenge_id == challenge.id
        ).first()

        if not user_challenge:
            return error_response(
                ErrorCode.NOT_FOUND,
                "챌린지에 참가하지 않았습니다."
            )

        if user_challenge.completed != 1:
            return error_response(
                ErrorCode.INVALID_STATE,
                "아직 챌린지를 완료하지 않았습니다."
            )

        if user_challenge.reward_claimed == 1:
            return error_response(
                ErrorCode.INVALID_STATE,
                "이미 보상을 수령했습니다."
            )

        # 보상 지급
        user, err = get_user_with_error(db, kakao_id)
        if err:
            return err

        try:
            user.cash = safe_add(user.cash, challenge.reward)
            user_challenge.reward_claimed = 1
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"챌린지 보상 지급 실패: {e}")
            return error_response(
                ErrorCode.INTERNAL_ERROR,
                "보상 지급 중 오류가 발생했습니다."
            )

        return success_response(
            f"🎉 챌린지 보상 {challenge.reward:,}원 지급!",
            reward=challenge.reward,
            cash=user.cash
        )

    @classmethod
    def get_leaderboard(cls, db: Session, limit: int = 10) -> List[Dict]:
        """챌린지 리더보드 (이번 주 진행률 기준)"""
        challenge = cls.get_or_create_weekly_challenge(db)
        if not challenge:
            return []

        # 진행률 높은 순으로 조회
        user_challenges = db.query(UserChallenge).filter(
            UserChallenge.challenge_id == challenge.id
        ).order_by(UserChallenge.current_value.desc()).limit(limit).all()

        # N+1 최적화: 유저 정보 배치 조회
        kakao_ids = [uc.kakao_id for uc in user_challenges]
        users_map = {}
        if kakao_ids:
            users = db.query(User).filter(User.kakao_id.in_(kakao_ids)).all()
            users_map = {u.kakao_id: u for u in users}

        result = []
        target = challenge.target_value if challenge.target_value > 0 else 1

        for rank, uc in enumerate(user_challenges, 1):
            user = users_map.get(uc.kakao_id)
            nickname = user.nickname if user and user.nickname else f"투자자{uc.kakao_id[-4:]}"
            progress_rate = min((uc.current_value / target) * 100, 100)

            result.append({
                "rank": rank,
                "nickname": nickname,
                "current_value": uc.current_value,
                "progress_rate": progress_rate,
                "completed": uc.completed == 1
            })

        return result
