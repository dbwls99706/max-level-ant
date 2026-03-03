"""
강화 시스템 서비스 — '투자의 검' 키우기

- 돈을 투자해서 검 레벨 강화
- 레벨이 높을수록 출석/복권 보상 증가
- 실패 시 레벨 하락 가능 → 전략적 판단 필요
"""
import random
from typing import Dict
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from config import EnhanceConfig, ErrorCode
from services.common import (
    get_user_with_error_for_update,
    error_response,
)
from utils import get_service_logger, log_game

logger = get_service_logger()


class EnhanceService:
    """강화 시스템 서비스"""

    @classmethod
    def get_enhance_info(cls, db: Session, kakao_id: str) -> Dict:
        """현재 강화 정보 조회"""
        user, error = get_user_with_error_for_update(db, kakao_id)
        if error:
            return error

        level = user.enhance_level or 0
        sword_name, sword_emoji = EnhanceConfig.get_sword_name(level)

        result = {
            "success": True,
            "level": level,
            "max_level": EnhanceConfig.MAX_LEVEL,
            "sword_name": sword_name,
            "sword_emoji": sword_emoji,
            "attendance_multiplier": EnhanceConfig.get_attendance_multiplier(level),
            "lottery_multiplier": EnhanceConfig.get_lottery_multiplier(level),
            "cash": user.cash,
        }

        # 다음 강화 정보 (만렙이 아닌 경우)
        if level < EnhanceConfig.MAX_LEVEL:
            result["next_cost"] = EnhanceConfig.get_cost(level)
            result["next_success_rate"] = EnhanceConfig.get_success_rate(level)
            fail_prob, fail_amount = EnhanceConfig.get_fail_penalty(level)
            result["fail_drop_prob"] = fail_prob
            result["fail_drop_amount"] = fail_amount

            # 다음 레벨의 검 이름
            next_name, next_emoji = EnhanceConfig.get_sword_name(level + 1)
            result["next_sword_name"] = next_name
            result["next_sword_emoji"] = next_emoji
        else:
            result["max_reached"] = True

        return result

    @classmethod
    def attempt_enhance(cls, db: Session, kakao_id: str) -> Dict:
        """
        강화 시도

        - 비용 차감
        - 성공률에 따라 성공/실패
        - 실패 시 레벨 하락 가능
        """
        user, error = get_user_with_error_for_update(db, kakao_id)
        if error:
            return error

        level = user.enhance_level or 0

        # 만렙 체크
        if level >= EnhanceConfig.MAX_LEVEL:
            sword_name, sword_emoji = EnhanceConfig.get_sword_name(level)
            return error_response(
                ErrorCode.INVALID_STATE,
                f"{sword_emoji} 이미 최고 레벨입니다!\n"
                f"'{sword_name}' Lv.{level} (MAX)"
            )

        # 비용 체크
        cost = EnhanceConfig.get_cost(level)
        if user.cash < cost:
            return error_response(
                ErrorCode.INSUFFICIENT_CASH,
                f"강화 비용이 부족합니다!\n"
                f"필요: {cost:,}원\n"
                f"보유: {user.cash:,}원\n"
                f"부족: {cost - user.cash:,}원"
            )

        # 비용 차감
        user.cash -= cost

        # 강화 시도
        success_rate = EnhanceConfig.get_success_rate(level)
        roll = random.randint(1, 100)
        succeeded = roll <= success_rate

        old_level = level
        old_name, old_emoji = EnhanceConfig.get_sword_name(old_level)

        if succeeded:
            # 성공!
            user.enhance_level = level + 1
            new_level = level + 1
            new_name, new_emoji = EnhanceConfig.get_sword_name(new_level)

            try:
                db.commit()
            except SQLAlchemyError as e:
                db.rollback()
                logger.error(f"강화 성공 DB 커밋 실패: {e}")
                return error_response(ErrorCode.DB_ERROR, "데이터베이스 오류가 발생했습니다.")

            log_game(
                kakao_id=kakao_id, game_type="ENHANCE",
                bet=cost, result=f"SUCCESS {old_level}→{new_level}",
                winnings=0, profit=-cost, cash_after=user.cash,
                extra=f"rate={success_rate}% roll={roll}"
            )

            # 레벨업으로 검 이름이 바뀌었는지 확인
            name_changed = old_name != new_name

            return {
                "success": True,
                "enhanced": True,
                "old_level": old_level,
                "new_level": new_level,
                "old_sword": old_name,
                "old_emoji": old_emoji,
                "new_sword": new_name,
                "new_emoji": new_emoji,
                "name_changed": name_changed,
                "cost": cost,
                "success_rate": success_rate,
                "cash": user.cash,
                "attendance_multiplier": EnhanceConfig.get_attendance_multiplier(new_level),
                "lottery_multiplier": EnhanceConfig.get_lottery_multiplier(new_level),
            }
        else:
            # 실패 — 레벨 하락 판정
            drop = 0
            fail_prob, fail_amount = EnhanceConfig.get_fail_penalty(level)

            if fail_prob > 0 and random.randint(1, 100) <= fail_prob:
                drop = fail_amount
                # 극한 구간 (16+): 20% 확률로 추가 -1
                if level >= 16 and random.randint(1, 100) <= 20:
                    drop += 1

            new_level = max(0, level - drop)
            user.enhance_level = new_level
            new_name, new_emoji = EnhanceConfig.get_sword_name(new_level)

            try:
                db.commit()
            except SQLAlchemyError as e:
                db.rollback()
                logger.error(f"강화 실패 DB 커밋 실패: {e}")
                return error_response(ErrorCode.DB_ERROR, "데이터베이스 오류가 발생했습니다.")

            log_game(
                kakao_id=kakao_id, game_type="ENHANCE",
                bet=cost, result=f"FAIL {old_level}→{new_level} drop={drop}",
                winnings=0, profit=-cost, cash_after=user.cash,
                extra=f"rate={success_rate}% roll={roll} drop={drop}"
            )

            return {
                "success": True,
                "enhanced": False,
                "old_level": old_level,
                "new_level": new_level,
                "drop": drop,
                "old_sword": old_name,
                "old_emoji": old_emoji,
                "new_sword": new_name,
                "new_emoji": new_emoji,
                "cost": cost,
                "success_rate": success_rate,
                "cash": user.cash,
                "attendance_multiplier": EnhanceConfig.get_attendance_multiplier(new_level),
                "lottery_multiplier": EnhanceConfig.get_lottery_multiplier(new_level),
            }
