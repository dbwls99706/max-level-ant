"""
각성 시스템 서비스 — 투자 감각 각성

- 돈을 투자해서 투자 능력 각성
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
    safe_subtract,
)
from utils import get_service_logger, log_game

logger = get_service_logger()


class EnhanceService:
    """각성 시스템 서비스"""

    @classmethod
    def get_enhance_info(cls, db: Session, kakao_id: str) -> Dict:
        """현재 각성 정보 조회"""
        from services.common import get_user_with_error
        user, error = get_user_with_error(db, kakao_id)
        if error:
            return error

        level = user.enhance_level or 0
        seed = getattr(user, 'enhance_title_seed', 0) or 0
        enhance_class = getattr(user, 'enhance_class', 0) or 0
        title_name, title_emoji = EnhanceConfig.get_title(level, seed=seed, enhance_class=enhance_class)

        class_info = EnhanceConfig.CLASS_INFO.get(enhance_class) if enhance_class else None

        result = {
            "success": True,
            "level": level,
            "max_level": EnhanceConfig.MAX_LEVEL,
            "title_name": title_name,
            "title_emoji": title_emoji,
            "enhance_class": enhance_class,
            "class_name": class_info["name"] if class_info else None,
            "class_emoji": class_info["emoji"] if class_info else None,
            "attendance_multiplier": EnhanceConfig.get_attendance_multiplier(level),
            "lottery_multiplier": EnhanceConfig.get_lottery_multiplier(level),
            "cash": user.cash,
        }

        # 다음 각성 정보 (만렙이 아닌 경우)
        if level < EnhanceConfig.MAX_LEVEL:
            result["next_cost"] = EnhanceConfig.get_cost(level)
            result["next_success_rate"] = EnhanceConfig.get_success_rate(level)
            fail_prob, fail_amount = EnhanceConfig.get_fail_penalty(level)
            result["fail_drop_prob"] = fail_prob
            result["fail_drop_amount"] = fail_amount

            # 다음 레벨 칭호
            next_name, next_emoji = EnhanceConfig.get_title(level + 1)
            result["next_title_name"] = next_name
            result["next_title_emoji"] = next_emoji
        else:
            result["max_reached"] = True

        return result

    @classmethod
    def attempt_enhance(cls, db: Session, kakao_id: str) -> Dict:
        """
        각성 시도

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
            seed = getattr(user, 'enhance_title_seed', 0) or 0
            title_name, title_emoji = EnhanceConfig.get_title(level, seed=seed)
            return error_response(
                ErrorCode.INVALID_STATE,
                f"{title_emoji} 이미 최고 경지에 도달했습니다!\n"
                f"'{title_name}' Lv.{level} (MAX)"
            )

        # 비용 체크
        cost = EnhanceConfig.get_cost(level)
        if user.cash < cost:
            return error_response(
                ErrorCode.INSUFFICIENT_CASH,
                f"각성 비용이 부족합니다!\n"
                f"필요: {cost:,}원\n"
                f"보유: {user.cash:,}원\n"
                f"부족: {cost - user.cash:,}원"
            )

        # 비용 차감
        user.cash = safe_subtract(user.cash, cost)

        # 각성 시도
        success_rate = EnhanceConfig.get_success_rate(level)
        roll = random.randint(1, 100)
        succeeded = roll <= success_rate

        old_level = level
        old_seed = getattr(user, 'enhance_title_seed', 0) or 0
        enhance_class = getattr(user, 'enhance_class', 0) or 0
        old_name, old_emoji = EnhanceConfig.get_title(old_level, seed=old_seed, enhance_class=enhance_class)

        if succeeded:
            # 성공!
            user.enhance_level = level + 1
            new_level = level + 1

            # 레벨 10 도달 시 직군 자동 랜덤 배정
            enhance_class = getattr(user, 'enhance_class', 0) or 0
            if new_level == EnhanceConfig.CLASS_LEVEL_THRESHOLD and not enhance_class:
                enhance_class = random.randint(1, 3)
                user.enhance_class = enhance_class

            # 직군 칭호는 후보가 3개이므로 seed 범위 0~2
            class_candidates = EnhanceConfig.get_class_candidates(new_level, enhance_class)
            seed_max = len(class_candidates) - 1 if class_candidates else 4
            new_seed = random.randint(0, seed_max)
            user.enhance_title_seed = new_seed
            new_name, new_emoji = EnhanceConfig.get_title(new_level, seed=new_seed, enhance_class=enhance_class)

            try:
                db.commit()
            except SQLAlchemyError as e:
                db.rollback()
                logger.error(f"각성 성공 DB 커밋 실패: {e}")
                return error_response(ErrorCode.DB_ERROR, "데이터베이스 오류가 발생했습니다.")

            log_game(
                kakao_id=kakao_id, game_type="ENHANCE",
                bet=cost, result=f"SUCCESS {old_level}→{new_level}",
                winnings=0, profit=-cost, cash_after=user.cash,
                extra=f"rate={success_rate}% roll={roll}"
            )

            # 주간 챌린지(각성 도전자) 진행도 갱신 (실패해도 각성에는 영향 없음)
            try:
                from services.challenge_service import ChallengeService
                ChallengeService.update_challenge_progress(db, kakao_id, "ENHANCE")
            except Exception as e:
                db.rollback()
                logger.warning(f"각성 챌린지 갱신 실패 ({kakao_id}): {e}")

            # 레벨업으로 칭호가 바뀌었는지 확인
            title_changed = old_name != new_name

            # 직군 배정 여부 (Lv.9→10 시 신규 배정)
            class_assigned = (new_level == EnhanceConfig.CLASS_LEVEL_THRESHOLD and enhance_class != 0
                              and (old_level < EnhanceConfig.CLASS_LEVEL_THRESHOLD))
            class_info = EnhanceConfig.CLASS_INFO.get(enhance_class) if enhance_class else None

            return {
                "success": True,
                "enhanced": True,
                "old_level": old_level,
                "new_level": new_level,
                "old_title": old_name,
                "old_emoji": old_emoji,
                "new_title": new_name,
                "new_emoji": new_emoji,
                "title_changed": title_changed,
                "cost": cost,
                "success_rate": success_rate,
                "cash": user.cash,
                "attendance_multiplier": EnhanceConfig.get_attendance_multiplier(new_level),
                "lottery_multiplier": EnhanceConfig.get_lottery_multiplier(new_level),
                "enhance_class": enhance_class,
                "class_name": class_info["name"] if class_info else None,
                "class_emoji": class_info["emoji"] if class_info else None,
                "class_assigned": class_assigned,
            }
        else:
            # 실패 — 레벨 0으로 초기화 (직군은 유지)
            drop = level  # 현재 레벨 전부 하락
            new_level = 0
            user.enhance_level = new_level
            new_seed = random.randint(0, 4)
            user.enhance_title_seed = new_seed
            # 레벨 0은 직군 무관 공통 칭호
            new_name, new_emoji = EnhanceConfig.get_title(new_level, seed=new_seed, enhance_class=0)

            try:
                db.commit()
            except SQLAlchemyError as e:
                db.rollback()
                logger.error(f"각성 실패 DB 커밋 실패: {e}")
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
                "old_title": old_name,
                "old_emoji": old_emoji,
                "new_title": new_name,
                "new_emoji": new_emoji,
                "cost": cost,
                "success_rate": success_rate,
                "cash": user.cash,
                "attendance_multiplier": EnhanceConfig.get_attendance_multiplier(new_level),
                "lottery_multiplier": EnhanceConfig.get_lottery_multiplier(new_level),
            }
