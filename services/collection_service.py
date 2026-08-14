"""
각성 도감 서비스

각성 실패로 레벨·직군·종은 사라지지만 도감은 남는다. 그게 이 게임의
영속 성장이다. 한 판의 성과가 전부 증발하면 다시 시작할 이유가 없다.
"""

import random
from typing import Dict, List, Optional, Tuple

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

import enhance_classes as ec
from enhance_art import CLASS_ART, FAMILIES, RARITY_ART
from models import ClassCollection
from utils import get_service_logger

logger = get_service_logger()

# 종 추첨용 목록. 매번 dict를 순회해 만들지 않도록 모듈 로드 시 한 번만 만든다.
# 순서를 고정해야 같은 시드에서 같은 결과가 나온다 (테스트 재현성).
_RARITY_KEYS: Tuple[str, ...] = tuple(RARITY_ART)
_RARITY_WEIGHTS: Tuple[float, ...] = tuple(ec.RARITY_ODDS[r][0] for r in _RARITY_KEYS)
_JOB_KEYS: Tuple[str, ...] = tuple(CLASS_ART)


class CollectionService:
    """도감 기록과 직군·종 추첨"""

    # ===========================================
    # 추첨
    # ===========================================
    @staticmethod
    def roll_job() -> str:
        """직군 추첨. 40개 모두 같은 확률이다.

        직군은 강약이 없고 그림과 정체성만 다르다. 희소성은 종이 담당하므로
        직군까지 가중치를 주면 '나쁜 직군'이 생겨 도감 수집이 벌칙이 된다.
        """
        return random.choice(_JOB_KEYS)

    @staticmethod
    def roll_rarity() -> str:
        """종 추첨. 노멀이 가장 두껍고 신화로 갈수록 얇아진다."""
        return random.choices(_RARITY_KEYS, weights=_RARITY_WEIGHTS, k=1)[0]

    @staticmethod
    def rarity_changed(before: Optional[str], after: str) -> int:
        """종 재추첨 결과 (1=상승, 0=유지, -1=하락).

        어느 쪽으로 움직였는지 알려주지 않으면 재추첨이 그냥 무작위 소음으로
        보인다. 등급 순서는 RARITY_ART의 선언 순서를 그대로 쓴다.
        """
        if before is None or before not in _RARITY_KEYS:
            return 0
        old_i = _RARITY_KEYS.index(before)
        new_i = _RARITY_KEYS.index(after)
        if new_i > old_i:
            return 1
        if new_i < old_i:
            return -1
        return 0

    # ===========================================
    # 기록
    # ===========================================
    @staticmethod
    def _already_unlocked(
        db: Session, kakao_id: str, job: str, rarity: str, growth: int
    ) -> bool:
        """이미 해금된 칸인지 미리 확인한다.

        이 검사는 최적화일 뿐 보장이 아니다. 동시 요청 둘이 함께 통과할 수
        있고, 그때는 유니크 제약이 막는다. 별도 메서드로 둔 이유는 그 경합
        상황을 테스트가 재현할 수 있어야 하기 때문이다.
        """
        return (
            db.query(ClassCollection.id)
            .filter(
                ClassCollection.kakao_id == kakao_id,
                ClassCollection.job == job,
                ClassCollection.rarity == rarity,
                ClassCollection.growth == growth,
            )
            .first()
            is not None
        )

    @classmethod
    def unlock(
        cls, db: Session, kakao_id: str, job: str, rarity: str, growth: int
    ) -> bool:
        """도감에 한 칸을 해금한다. 새로 열렸으면 True.

        커밋은 하지 않는다. 각성 결과와 같은 트랜잭션에서 함께 확정돼야
        "각성은 성공했는데 도감에는 안 남는" 상태가 생기지 않는다.

        대신 삽입은 SAVEPOINT 안에서 한다. 도감 기록이 실패했다고
        `db.rollback()`을 부르면 바깥 트랜잭션까지 되감겨서 레벨업과
        비용 차감이 통째로 사라진다. 도감은 부가 기록이지 각성의 조건이
        아니므로, 실패해도 각성 자체는 살아남아야 한다.
        """
        if job not in CLASS_ART or rarity not in RARITY_ART:
            return False
        if growth not in ec.GROWTH_STAGES:
            return False

        if cls._already_unlocked(db, kakao_id, job, rarity, growth):
            return False

        try:
            with db.begin_nested():
                db.add(
                    ClassCollection(
                        kakao_id=kakao_id, job=job, rarity=rarity, growth=growth
                    )
                )
        except IntegrityError:
            # 동시 요청이 같은 칸을 먼저 넣었다. 이미 해금된 것이므로 실패가 아니다.
            return False
        except SQLAlchemyError as e:
            logger.warning(f"도감 기록 실패 ({kakao_id} {job}/{rarity}/g{growth}): {e}")
            return False
        return True

    # ===========================================
    # 조회
    # ===========================================
    @classmethod
    def get_entries(cls, db: Session, kakao_id: str) -> List[ClassCollection]:
        return (
            db.query(ClassCollection).filter(ClassCollection.kakao_id == kakao_id).all()
        )

    @classmethod
    def get_summary(cls, db: Session, kakao_id: str) -> Dict:
        """도감 진행도.

        전체 칸 수는 데이터에서 센다. 상수로 박아두면 직군을 추가했을 때
        "601칸 중 600칸"처럼 영영 100%가 안 되는 도감이 된다.
        """
        entries = cls.get_entries(db, kakao_id)
        total = len(CLASS_ART) * len(RARITY_ART) * len(ec.GROWTH_STAGES)

        by_family: Dict[str, Dict[str, int]] = {
            key: {
                "owned": 0,
                "total": len(ec.classes_of(key))
                * len(RARITY_ART)
                * len(ec.GROWTH_STAGES),
            }
            for key in FAMILIES
        }
        by_rarity: Dict[str, int] = {r: 0 for r in RARITY_ART}
        jobs_seen = set()

        for e in entries:
            if e.job not in CLASS_ART:
                continue  # 직군이 삭제된 옛 기록은 집계에서 제외한다
            family = CLASS_ART[e.job][0]
            by_family[family]["owned"] += 1
            if e.rarity in by_rarity:
                by_rarity[e.rarity] += 1
            jobs_seen.add(e.job)

        owned = sum(f["owned"] for f in by_family.values())
        return {
            "owned": owned,
            "total": total,
            "percent": round(owned / total * 100, 1) if total else 0.0,
            "jobs_owned": len(jobs_seen),
            "jobs_total": len(CLASS_ART),
            "by_family": by_family,
            "by_rarity": by_rarity,
        }

    @classmethod
    def get_family_detail(cls, db: Session, kakao_id: str, family: str) -> Dict:
        """계열 하나의 직군별 수집 현황"""
        owned = {
            (e.job, e.rarity, e.growth)
            for e in cls.get_entries(db, kakao_id)
            if e.job in CLASS_ART
        }
        per_job = len(RARITY_ART) * len(ec.GROWTH_STAGES)

        jobs = []
        for job in ec.classes_of(family):
            count = sum(1 for j, _r, _g in owned if j == job)
            best = None
            for rarity in reversed(_RARITY_KEYS):  # 높은 종부터
                if any(j == job and r == rarity for j, r, _g in owned):
                    best = rarity
                    break
            jobs.append(
                {
                    "job": job,
                    "label": ec.class_label(job),
                    "owned": count,
                    "total": per_job,
                    "best_rarity": best,
                }
            )
        return {"family": family, "jobs": jobs}
