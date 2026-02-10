"""
마일스톤 서비스 - 자산 달성 보너스 (리팩토링)
- 트랜잭션 안전성 강화
- next() 안전화
"""
from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from models import Milestone, User
from services.common import (
    get_user_with_error_for_update,
    error_response,
    success_response,
    safe_add,
)
from config import ErrorCode
from utils import get_service_logger

logger = get_service_logger()


class MilestoneService:
    """마일스톤 시스템"""

    # 마일스톤 정의
    MILESTONES = {
        # 자산 달성 마일스톤
        "ASSET_10M": {
            "name": "🌱 천만장자",
            "description": "총 자산 1,000만원 달성",
            "threshold": 10_000_000,
            "reward": 500_000,
            "category": "asset"
        },
        "ASSET_30M": {
            "name": "📈 삼천만원 돌파",
            "description": "총 자산 3,000만원 달성",
            "threshold": 30_000_000,
            "reward": 1_000_000,
            "category": "asset"
        },
        "ASSET_50M": {
            "name": "⭐ 오천만원 클럽",
            "description": "총 자산 5,000만원 달성",
            "threshold": 50_000_000,
            "reward": 2_000_000,
            "category": "asset"
        },
        "ASSET_100M": {
            "name": "🏆 억만장자",
            "description": "총 자산 1억원 달성",
            "threshold": 100_000_000,
            "reward": 5_000_000,
            "category": "asset"
        },
        "ASSET_500M": {
            "name": "👑 자산왕",
            "description": "총 자산 5억원 달성",
            "threshold": 500_000_000,
            "reward": 20_000_000,
            "category": "asset"
        },
        "ASSET_1B": {
            "name": "💎 전설의 투자자",
            "description": "총 자산 10억원 달성",
            "threshold": 1_000_000_000,
            "reward": 50_000_000,
            "category": "asset"
        },
        # 거래 마일스톤
        "TRADE_10": {
            "name": "🔰 거래 입문",
            "description": "총 10회 거래 달성",
            "threshold": 10,
            "reward": 100_000,
            "category": "trade"
        },
        "TRADE_50": {
            "name": "📊 활발한 트레이더",
            "description": "총 50회 거래 달성",
            "threshold": 50,
            "reward": 500_000,
            "category": "trade"
        },
        "TRADE_100": {
            "name": "🔥 거래의 달인",
            "description": "총 100회 거래 달성",
            "threshold": 100,
            "reward": 1_000_000,
            "category": "trade"
        },
        "TRADE_500": {
            "name": "⚡ 거래 마스터",
            "description": "총 500회 거래 달성",
            "threshold": 500,
            "reward": 3_000_000,
            "category": "trade"
        },
        # 출석 마일스톤
        "STREAK_7": {
            "name": "📅 1주 연속 출석",
            "description": "7일 연속 출석 달성",
            "threshold": 7,
            "reward": 500_000,
            "category": "streak"
        },
        "STREAK_30": {
            "name": "🗓️ 1달 연속 출석",
            "description": "30일 연속 출석 달성",
            "threshold": 30,
            "reward": 3_000_000,
            "category": "streak"
        },
        "STREAK_100": {
            "name": "🏅 100일 연속 출석",
            "description": "100일 연속 출석 달성",
            "threshold": 100,
            "reward": 10_000_000,
            "category": "streak"
        }
    }

    @classmethod
    def check_milestones(
        cls,
        db: Session,
        kakao_id: str,
        total_asset: int = None,
        total_trades: int = None,
        streak: int = None
    ) -> List[Dict]:
        """
        마일스톤 달성 체크
        Returns: 새로 달성한 마일스톤 리스트
        """
        user = db.query(User).filter(User.kakao_id == kakao_id).first()
        if not user:
            return []

        achieved = []

        # 이미 달성한 마일스톤 배치 조회 (N+1 방지: 13개 개별 쿼리 → 1개)
        existing_milestones = db.query(Milestone.milestone_type).filter(
            Milestone.kakao_id == kakao_id
        ).all()
        achieved_types = {m.milestone_type for m in existing_milestones}

        for milestone_type, info in cls.MILESTONES.items():
            if milestone_type in achieved_types:
                continue

            # 카테고리별 체크
            should_achieve = False
            current_value = 0

            if info["category"] == "asset" and total_asset is not None:
                if total_asset >= info["threshold"]:
                    should_achieve = True
                    current_value = total_asset

            elif info["category"] == "trade" and total_trades is not None:
                if total_trades >= info["threshold"]:
                    should_achieve = True
                    current_value = total_trades

            elif info["category"] == "streak" and streak is not None:
                if streak >= info["threshold"]:
                    should_achieve = True
                    current_value = streak

            if should_achieve:
                # 마일스톤 달성 기록
                milestone = Milestone(
                    kakao_id=kakao_id,
                    milestone_type=milestone_type,
                    asset_at_achievement=current_value,
                    reward_claimed=0
                )
                db.add(milestone)

                achieved.append({
                    "type": milestone_type,
                    "name": info["name"],
                    "description": info["description"],
                    "reward": info["reward"]
                })

        if achieved:
            try:
                db.commit()
            except SQLAlchemyError as e:
                db.rollback()
                logger.error(f"마일스톤 달성 기록 DB 실패: {e}")
                return []

        return achieved

    @classmethod
    def get_user_milestones(cls, db: Session, kakao_id: str) -> Dict:
        """유저의 마일스톤 현황"""
        achieved_milestones = db.query(Milestone).filter(
            Milestone.kakao_id == kakao_id
        ).all()

        achieved_types = {m.milestone_type for m in achieved_milestones}

        result = {
            "achieved": [],
            "pending": [],
            "unclaimed_rewards": 0
        }

        for m_type, info in cls.MILESTONES.items():
            milestone_data = {
                "type": m_type,
                "name": info["name"],
                "description": info["description"],
                "threshold": info["threshold"],
                "reward": info["reward"],
                "category": info["category"]
            }

            if m_type in achieved_types:
                # 안전한 검색: next()에 기본값 제공
                milestone = next(
                    (m for m in achieved_milestones if m.milestone_type == m_type),
                    None
                )
                if milestone:
                    milestone_data["achieved_at"] = str(milestone.achieved_at)
                    milestone_data["reward_claimed"] = milestone.reward_claimed == 1

                    if not milestone_data["reward_claimed"]:
                        result["unclaimed_rewards"] += info["reward"]

                result["achieved"].append(milestone_data)
            else:
                result["pending"].append(milestone_data)

        return result

    @classmethod
    def claim_milestone_reward(cls, db: Session, kakao_id: str, milestone_type: str) -> Dict:
        """마일스톤 보상 수령"""
        if milestone_type not in cls.MILESTONES:
            return error_response(
                ErrorCode.NOT_FOUND,
                "존재하지 않는 마일스톤입니다."
            )

        milestone = db.query(Milestone).filter(
            Milestone.kakao_id == kakao_id,
            Milestone.milestone_type == milestone_type
        ).first()

        if not milestone:
            return error_response(
                ErrorCode.NOT_FOUND,
                "아직 달성하지 않은 마일스톤입니다."
            )

        if milestone.reward_claimed == 1:
            return error_response(
                ErrorCode.INVALID_STATE,
                "이미 보상을 수령했습니다."
            )

        # 보상 지급 (FOR UPDATE로 동시 수령 방지)
        user, err = get_user_with_error_for_update(db, kakao_id)
        if err:
            return err

        reward = cls.MILESTONES[milestone_type]["reward"]

        try:
            user.cash = safe_add(user.cash, reward)
            milestone.reward_claimed = 1
            db.commit()
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"마일스톤 보상 지급 DB 실패: {e}")
            return error_response(
                ErrorCode.INTERNAL_ERROR,
                "보상 지급 중 오류가 발생했습니다."
            )

        return success_response(
            f"🏆 {cls.MILESTONES[milestone_type]['name']} 보상 수령!",
            milestone=cls.MILESTONES[milestone_type]["name"],
            reward=reward,
            cash=user.cash
        )

    @classmethod
    def claim_all_rewards(cls, db: Session, kakao_id: str) -> Dict:
        """모든 미수령 마일스톤 보상 수령"""
        milestones = db.query(Milestone).filter(
            Milestone.kakao_id == kakao_id,
            Milestone.reward_claimed == 0
        ).all()

        if not milestones:
            return error_response(
                ErrorCode.NOT_FOUND,
                "수령할 보상이 없습니다."
            )

        user, err = get_user_with_error_for_update(db, kakao_id)
        if err:
            return err

        total_reward = 0
        claimed_milestones = []

        try:
            for m in milestones:
                # 안전한 접근: milestone_type이 MILESTONES에 없을 수 있음
                milestone_info = cls.MILESTONES.get(m.milestone_type)
                if not milestone_info:
                    logger.warning(f"알 수 없는 마일스톤 타입: {m.milestone_type}")
                    continue

                reward = milestone_info["reward"]
                user.cash = safe_add(user.cash, reward)
                total_reward += reward
                m.reward_claimed = 1
                claimed_milestones.append(milestone_info["name"])

            db.commit()
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"마일스톤 일괄 보상 지급 DB 실패: {e}")
            return error_response(
                ErrorCode.INTERNAL_ERROR,
                "보상 지급 중 오류가 발생했습니다."
            )

        if not claimed_milestones:
            return error_response(
                ErrorCode.NOT_FOUND,
                "수령할 보상이 없습니다."
            )

        return success_response(
            f"🎉 {len(claimed_milestones)}개 마일스톤 보상 수령!",
            total_reward=total_reward,
            count=len(claimed_milestones),
            milestones=claimed_milestones,
            cash=user.cash
        )

    @classmethod
    def get_next_milestone(cls, db: Session, kakao_id: str, category: str = "asset") -> Optional[Dict]:
        """다음 달성 가능한 마일스톤 조회"""
        achieved_milestones = db.query(Milestone).filter(
            Milestone.kakao_id == kakao_id
        ).all()

        achieved_types = {m.milestone_type for m in achieved_milestones}

        # 해당 카테고리에서 미달성 마일스톤 중 threshold가 가장 낮은 것 찾기
        candidates = [
            (m_type, info)
            for m_type, info in cls.MILESTONES.items()
            if info["category"] == category and m_type not in achieved_types
        ]

        if not candidates:
            return None

        # threshold 기준 정렬
        candidates.sort(key=lambda x: x[1]["threshold"])
        m_type, info = candidates[0]

        return {
            "type": m_type,
            "name": info["name"],
            "description": info["description"],
            "threshold": info["threshold"],
            "reward": info["reward"]
        }
