"""
주간 챌린지 서비스 (리팩토링)
- 트랜잭션 안전성 강화
- 0 나누기 방지
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import random
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from models import WeeklyChallenge, UserChallenge, User, AssetHistory
from services.common import (
    get_user_with_error_for_update,
    error_response,
    success_response,
    safe_add,
)
from config import ErrorCode, KST
from utils import get_service_logger

logger = get_service_logger()


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
        "ENHANCE": {
            "name": "각성 도전자",
            "description": "각성 {target}회 성공하기",
            "targets": [3, 5, 8],
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
        today = datetime.now(KST).date()
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
        today = datetime.now(KST).date()
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
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"주간 챌린지 생성 DB 실패: {e}")
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
            except SQLAlchemyError as e:
                db.rollback()
                logger.error(f"유저 챌린지 기록 생성 DB 실패: {e}")
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
        카운트형 챌린지 진행도 업데이트 (TRADE_COUNT, ATTENDANCE, ENHANCE)
        거래 완료, 출석 완료, 각성 성공 등 이벤트 발생 시 호출
        """
        challenge = cls.get_or_create_weekly_challenge(db)
        if not challenge or challenge.challenge_type != challenge_type:
            return None

        return cls._apply_challenge_value(
            db, kakao_id, challenge, increment=increment
        )

    @classmethod
    def update_asset_challenges(
        cls,
        db: Session,
        kakao_id: str,
        total_asset: Optional[int]
    ) -> Optional[Dict]:
        """
        지표형 챌린지 진행도 업데이트 (PROFIT_RATE, ASSET_GROWTH)
        - 이번 주 시작 시점 자산(AssetHistory) 대비 증가분으로 계산
        - 거래/출석 등 총자산이 계산되는 이벤트에서 호출
        """
        if total_asset is None:
            return None

        challenge = cls.get_or_create_weekly_challenge(db)
        if not challenge or challenge.challenge_type not in ("PROFIT_RATE", "ASSET_GROWTH"):
            return None

        baseline = cls._get_week_baseline_asset(db, kakao_id, challenge.start_date)
        if not baseline or baseline <= 0:
            return None

        growth = total_asset - baseline
        if challenge.challenge_type == "PROFIT_RATE":
            value = int((growth / baseline) * 100)  # % 단위
        else:
            value = growth // 10_000  # 만원 단위

        if value <= 0:
            return None

        return cls._apply_challenge_value(db, kakao_id, challenge, set_value=value)

    @classmethod
    def _get_week_baseline_asset(cls, db: Session, kakao_id: str, week_start) -> Optional[int]:
        """이번 주 시작 시점 자산 (주 시작 후 첫 기록 → 주 시작 전 마지막 기록 → 초기 자금)"""
        first_this_week = db.query(AssetHistory).filter(
            AssetHistory.kakao_id == kakao_id,
            AssetHistory.record_date >= week_start
        ).order_by(AssetHistory.record_date.asc()).first()
        if first_this_week:
            return first_this_week.total_asset

        last_before = db.query(AssetHistory).filter(
            AssetHistory.kakao_id == kakao_id,
            AssetHistory.record_date < week_start
        ).order_by(AssetHistory.record_date.desc()).first()
        if last_before:
            return last_before.total_asset

        user = db.query(User).filter(User.kakao_id == kakao_id).first()
        return user.initial_cash if user else None

    @classmethod
    def _apply_challenge_value(
        cls,
        db: Session,
        kakao_id: str,
        challenge: WeeklyChallenge,
        increment: int = 0,
        set_value: Optional[int] = None
    ) -> Optional[Dict]:
        """챌린지 진행값 적용 (increment: 누적, set_value: 최대값 갱신) 및 완료 처리"""
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

        try:
            if set_value is not None:
                user_challenge.current_value = max(user_challenge.current_value or 0, set_value)
            else:
                user_challenge.current_value = (user_challenge.current_value or 0) + increment

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
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"챌린지 진행도 업데이트 DB 실패: {e}")

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

        # 보상 지급 (FOR UPDATE로 동시 수령 방지)
        user, err = get_user_with_error_for_update(db, kakao_id)
        if err:
            return err

        try:
            user.cash = safe_add(user.cash, challenge.reward)
            user_challenge.reward_claimed = 1
            db.commit()
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"챌린지 보상 지급 DB 실패: {e}")
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
