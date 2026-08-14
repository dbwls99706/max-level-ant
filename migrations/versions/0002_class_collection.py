"""각성 도감 - 직군/종 컬럼과 수집 기록 테이블

users에 직군(enhance_job)과 종(enhance_rarity)을 추가하고,
해금한 조합을 남기는 class_collections를 만든다.

기존 유저의 3계열 값(enhance_class: 1=트레이더, 2=투자가, 3=퀀트)은
같은 계열의 대표 직군으로 옮긴다. 계열은 지키면서 새 체계로 넘어가는
가장 덜 놀라운 선택이다. 그냥 비워두면 Lv.10 이상 유저의 정체성이
말없이 사라진다.

enhance_class 컬럼 자체는 남긴다. 옮긴 데이터가 맞는지 운영에서 확인한 뒤
별도 리비전에서 제거한다. 되돌릴 수 없는 일을 한 번에 하지 않는다.

Revision ID: 0002_class_collection
Revises: 0001_baseline
Create Date: 2026-08-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_class_collection"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 옛 계열 코드 -> 새 직군 키.
# 각 계열의 첫 직군을 대표로 삼는다. 리비전은 과거 시점에 고정돼야 하므로
# enhance_art를 import하지 않고 값을 직접 적는다 (직군 키가 나중에 바뀌어도
# 이미 실행된 마이그레이션의 의미가 달라지면 안 된다).
_LEGACY_CLASS_TO_JOB = {
    1: "scalper",  # 트레이더
    2: "valuehunter",  # 투자가
    3: "factor",  # 퀀트
}

_NEW_USER_COLUMNS = [
    ("enhance_job", sa.String(length=32)),
    ("enhance_rarity", sa.String(length=16)),
]


def _user_columns(bind) -> set:
    return {c["name"] for c in sa.inspect(bind).get_columns("users")}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. users 컬럼 추가 (이미 있으면 건너뛴다 - _migrate_db가 먼저 붙였을 수 있다)
    existing = _user_columns(bind)
    for name, type_ in _NEW_USER_COLUMNS:
        if name not in existing:
            op.add_column("users", sa.Column(name, type_, nullable=True))

    # 2. 기존 계열 값을 직군으로 옮긴다.
    #    이미 직군이 있는 행은 건드리지 않는다 (재실행해도 안전).
    if "enhance_class" in existing:
        for legacy, job in _LEGACY_CLASS_TO_JOB.items():
            op.execute(
                sa.text(
                    "UPDATE users SET enhance_job = :job "
                    "WHERE enhance_class = :legacy AND enhance_job IS NULL"
                ).bindparams(job=job, legacy=legacy)
            )

        # 직군이 생겼는데 종이 없으면 가장 흔한 종을 준다.
        # 종 없이 직군만 있으면 이미지 좌표가 반쪽이라 카드를 못 만든다.
        op.execute(
            sa.text(
                "UPDATE users SET enhance_rarity = 'normal' "
                "WHERE enhance_job IS NOT NULL AND enhance_rarity IS NULL"
            )
        )

    # 3. 도감 테이블
    if "class_collections" not in inspector.get_table_names():
        op.create_table(
            "class_collections",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("kakao_id", sa.String(length=100), nullable=False),
            sa.Column("job", sa.String(length=32), nullable=False),
            sa.Column("rarity", sa.String(length=16), nullable=False),
            sa.Column("growth", sa.Integer(), nullable=False),
            sa.Column("unlocked_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["kakao_id"], ["users.kakao_id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "kakao_id", "job", "rarity", "growth", name="unique_collection_entry"
            ),
        )
        op.create_index(
            "ix_class_collections_kakao_id", "class_collections", ["kakao_id"]
        )
        op.create_index("ix_collection_user", "class_collections", ["kakao_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "class_collections" in inspector.get_table_names():
        op.drop_index("ix_collection_user", table_name="class_collections")
        op.drop_index("ix_class_collections_kakao_id", table_name="class_collections")
        op.drop_table("class_collections")

    existing = _user_columns(bind)
    for name, _type in _NEW_USER_COLUMNS:
        if name in existing:
            op.drop_column("users", name)
