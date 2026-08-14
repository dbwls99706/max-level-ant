"""
각성 시스템 서비스 - 투자 감각 각성

- 돈을 투자해서 투자 능력 각성
- 레벨이 높을수록 출석/복권 보상 증가
- 실패 시 레벨·직군·종이 모두 초기화 → 전략적 판단 필요
- 도감 기록은 실패해도 남는다 (판을 넘어 남는 유일한 자산)
"""

import random
from typing import Dict
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

import enhance_classes as ec
from enhance_config import EnhanceConfig
from errors import ErrorCode
from services.collection_service import CollectionService
from services.common import (
    get_user_with_error_for_update,
    error_response,
    safe_subtract,
)
from utils import get_service_logger, log_game

logger = get_service_logger()


class EnhanceService:
    """각성 시스템 서비스"""

    @staticmethod
    def _identity(user, level: int) -> Dict:
        """직군·종·성장과 그에 딸린 이미지·문구.

        직군이 아직 없으면(Lv.10 미만) 전부 None이다. 호출부는 이 경우
        이미지 없이 텍스트로만 응답해야 한다.
        """
        job = getattr(user, "enhance_job", None)
        rarity = getattr(user, "enhance_rarity", None)
        growth = ec.growth_stage(level, EnhanceConfig.MAX_LEVEL)

        if not job or not rarity:
            return {
                "job": None,
                "job_label": None,
                "family_name": None,
                "family_emoji": None,
                "rarity": None,
                "rarity_label": None,
                "rarity_bonus": 0.0,
                "growth": growth,
                "growth_name": ec.GROWTH_STAGES[growth],
                "art_stem": None,
                "flavor": None,
            }

        family_name, family_emoji = ec.class_family(job)
        return {
            "job": job,
            "job_label": ec.class_label(job),
            "family_name": family_name,
            "family_emoji": family_emoji,
            "rarity": rarity,
            "rarity_label": ec.rarity_label(rarity),
            "rarity_bonus": ec.rarity_bonus(rarity),
            "growth": growth,
            "growth_name": ec.GROWTH_STAGES[growth],
            "art_stem": ec.art_stem(job, rarity, growth),
            "flavor": ec.awakening_flavor(job, rarity, growth),
        }

    @classmethod
    def get_enhance_info(cls, db: Session, kakao_id: str) -> Dict:
        """현재 각성 정보 조회"""
        from services.common import get_user_with_error

        user, error = get_user_with_error(db, kakao_id)
        if error:
            return error

        level = user.enhance_level or 0
        seed = getattr(user, "enhance_title_seed", 0) or 0
        title_name, title_emoji = EnhanceConfig.get_title(level, seed=seed)

        result = {
            "success": True,
            "level": level,
            "max_level": EnhanceConfig.MAX_LEVEL,
            "title_name": title_name,
            "title_emoji": title_emoji,
            "attendance_multiplier": EnhanceConfig.get_attendance_multiplier(level),
            "lottery_multiplier": EnhanceConfig.get_lottery_multiplier(level),
            "cash": user.cash,
        }
        result.update(cls._identity(user, level))

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
            seed = getattr(user, "enhance_title_seed", 0) or 0
            title_name, title_emoji = EnhanceConfig.get_title(level, seed=seed)
            return error_response(
                ErrorCode.INVALID_STATE,
                f"{title_emoji} 이미 최고 경지에 도달했습니다!\n"
                f"'{title_name}' Lv.{level} (MAX)",
            )

        # 비용 체크
        cost = EnhanceConfig.get_cost(level)
        if user.cash < cost:
            return error_response(
                ErrorCode.INSUFFICIENT_CASH,
                f"각성 비용이 부족합니다!\n"
                f"필요: {cost:,}원\n"
                f"보유: {user.cash:,}원\n"
                f"부족: {cost - user.cash:,}원",
            )

        # 비용 차감
        user.cash = safe_subtract(user.cash, cost)

        # 각성 시도
        success_rate = EnhanceConfig.get_success_rate(level)
        roll = random.randint(1, 100)
        succeeded = roll <= success_rate

        old_level = level
        old_seed = getattr(user, "enhance_title_seed", 0) or 0
        old_name, old_emoji = EnhanceConfig.get_title(old_level, seed=old_seed)
        old_rarity = getattr(user, "enhance_rarity", None)
        old_growth = ec.growth_stage(old_level, EnhanceConfig.MAX_LEVEL)

        if succeeded:
            # 성공!
            user.enhance_level = level + 1
            new_level = level + 1

            # 직군 배정 - 이 레벨에 처음 도달했을 때 한 번.
            # 실패로 0이 되면 직군이 풀리므로 다음 도달에서 다시 뽑힌다.
            job_assigned = False
            if new_level >= EnhanceConfig.CLASS_LEVEL_THRESHOLD and not getattr(
                user, "enhance_job", None
            ):
                user.enhance_job = CollectionService.roll_job()
                user.enhance_rarity = CollectionService.roll_rarity()
                job_assigned = True

            # 종 재추첨 - 정해진 레벨을 밟을 때마다 한 번.
            # 올라갈 수도 내려갈 수도 있다. 그래야 신화가 계속 긴장을 준다.
            rarity_rerolled = False
            rarity_delta = 0
            if (
                not job_assigned
                and getattr(user, "enhance_job", None)
                and new_level in ec.RARITY_REROLL_LEVELS
            ):
                rolled = CollectionService.roll_rarity()
                rarity_delta = CollectionService.rarity_changed(old_rarity, rolled)
                user.enhance_rarity = rolled
                rarity_rerolled = True

            new_seed = random.randint(0, 4)
            user.enhance_title_seed = new_seed
            new_name, new_emoji = EnhanceConfig.get_title(new_level, seed=new_seed)

            # 도감 기록 - 커밋 전에 같은 트랜잭션에 넣는다.
            # 각성은 됐는데 도감에는 안 남는 상태를 만들지 않기 위해서다.
            identity = cls._identity(user, new_level)
            newly_unlocked = False
            if identity["job"] and identity["rarity"]:
                newly_unlocked = CollectionService.unlock(
                    db,
                    kakao_id,
                    identity["job"],
                    identity["rarity"],
                    identity["growth"],
                )

            try:
                db.commit()
            except SQLAlchemyError as e:
                db.rollback()
                logger.error(f"각성 성공 DB 커밋 실패: {e}")
                return error_response(
                    ErrorCode.DB_ERROR, "데이터베이스 오류가 발생했습니다."
                )

            log_game(
                kakao_id=kakao_id,
                game_type="ENHANCE",
                bet=cost,
                result=f"SUCCESS {old_level}→{new_level}",
                winnings=0,
                profit=-cost,
                cash_after=user.cash,
                extra=f"rate={success_rate}% roll={roll}",
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

            result = {
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
                "attendance_multiplier": EnhanceConfig.get_attendance_multiplier(
                    new_level
                ),
                "lottery_multiplier": EnhanceConfig.get_lottery_multiplier(new_level),
                # 도감 관련
                "job_assigned": job_assigned,
                "rarity_rerolled": rarity_rerolled,
                "rarity_delta": rarity_delta,
                "old_rarity": old_rarity,
                "newly_unlocked": newly_unlocked,
                # 성장 단계가 올라가면 같은 직군·종이라도 그림이 바뀐다
                "growth_changed": identity["growth"] != old_growth,
            }
            result.update(identity)
            return result
        else:
            # 실패 - 레벨 0으로 초기화
            drop = level  # 현재 레벨 전부 하락
            new_level = 0
            user.enhance_level = new_level

            # 직군과 종도 같이 풀린다. 다음에 Lv.10에 도달하면 새로 뽑으므로,
            # 실패는 곧 다른 직군으로 갈아탈 기회이기도 하다.
            # 도감 기록은 지우지 않는다. 그게 판을 넘어 남는 유일한 자산이다.
            lost_job = getattr(user, "enhance_job", None)
            lost_rarity = getattr(user, "enhance_rarity", None)
            user.enhance_job = None
            user.enhance_rarity = None

            new_seed = random.randint(0, 4)
            user.enhance_title_seed = new_seed
            new_name, new_emoji = EnhanceConfig.get_title(new_level, seed=new_seed)

            try:
                db.commit()
            except SQLAlchemyError as e:
                db.rollback()
                logger.error(f"각성 실패 DB 커밋 실패: {e}")
                return error_response(
                    ErrorCode.DB_ERROR, "데이터베이스 오류가 발생했습니다."
                )

            log_game(
                kakao_id=kakao_id,
                game_type="ENHANCE",
                bet=cost,
                result=f"FAIL {old_level}→{new_level} drop={drop}",
                winnings=0,
                profit=-cost,
                cash_after=user.cash,
                extra=f"rate={success_rate}% roll={roll} drop={drop}",
            )

            result = {
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
                "attendance_multiplier": EnhanceConfig.get_attendance_multiplier(
                    new_level
                ),
                "lottery_multiplier": EnhanceConfig.get_lottery_multiplier(new_level),
                # 무엇을 잃었는지 알려줘야 실패가 사건이 된다
                "lost_job": ec.class_label(lost_job) if lost_job else None,
                "lost_rarity": ec.rarity_label(lost_rarity) if lost_rarity else None,
            }
            result.update(cls._identity(user, new_level))
            return result
