"""baseline schema

Alembic 도입 시점의 전체 스키마.

이 마이그레이션은 **멱등하게** 동작해야 한다. 이 프로젝트는 Alembic 이전에
`Base.metadata.create_all()` + `database._migrate_db()`로 스키마를 관리했고,
운영 DB에는 이미 대부분의 테이블·컬럼이 존재하기 때문이다. 따라서
  - 이미 있는 테이블은 만들지 않고
  - users에 빠진 컬럼만 채우고
  - PostgreSQL의 int4 금액 컬럼만 int8로 넓힌다.
그래서 새 DB(전체 생성)와 기존 운영 DB(대부분 no-op) 양쪽에서 안전하다.

주의: 각 테이블 정의는 이 리비전 시점에 **고정**된 것이다. 모델이 바뀌면
여기를 고치지 말고 새 리비전을 추가해야 한다. (여기서 Base.metadata를
참조하면 미래의 스키마를 과거 리비전이 만들어버리는 사고가 난다.)

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Alembic 이전 `_migrate_db()`가 users에 붙이던 컬럼들.
# 아주 오래된 DB에는 빠져 있을 수 있어 baseline에서 한 번 더 맞춘다.
_USER_COLUMNS = [
    ("last_mission_date", sa.Date()),
    ("daily_trade_count", sa.Integer()),
    ("mission_completed", sa.Integer()),
    ("achievements", sa.String(length=1000)),
    ("total_profit_realized", sa.BigInteger()),
    ("total_trades", sa.Integer()),
    ("last_lottery_date", sa.Date()),
    ("lottery_count_today", sa.Integer()),
    ("nickname_change_count", sa.Integer()),
    ("last_nickname_change", sa.Date()),
    ("updown_active", sa.Integer()),
    ("updown_bet", sa.BigInteger()),
    ("updown_current_number", sa.Integer()),
    ("updown_round", sa.Integer()),
    ("updown_multiplier", sa.Float()),
    ("enhance_level", sa.Integer()),
    ("enhance_title_seed", sa.Integer()),
    ("enhance_class", sa.Integer()),
    ("pending_quiz", sa.String(length=2000)),
    ("pending_quiz_bet", sa.BigInteger()),
]

# 거래 금액에 비례해 int4 상한을 넘길 수 있는 컬럼 (PostgreSQL 전용)
_WIDEN_TO_BIGINT = [
    ("transactions", "fee"),
    ("holdings", "avg_price"),
]


def _create_api_tokens() -> None:
    op.create_table(
        "api_tokens",
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("provider"),
    )


def _create_stock_cache() -> None:
    op.create_table(
        "stock_cache",
        sa.Column("stock_code", sa.String(length=20), nullable=False),
        sa.Column("stock_name", sa.String(length=100), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("stock_code"),
    )


def _create_users() -> None:
    op.create_table(
        "users",
        sa.Column("kakao_id", sa.String(length=100), nullable=False),
        sa.Column("nickname", sa.String(length=100), nullable=True),
        sa.Column("nickname_change_count", sa.Integer(), nullable=True),
        sa.Column("last_nickname_change", sa.Date(), nullable=True),
        sa.Column("cash", sa.BigInteger(), nullable=True),
        sa.Column("initial_cash", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("last_attendance", sa.Date(), nullable=True),
        sa.Column("attendance_streak", sa.Integer(), nullable=True),
        sa.Column("last_ad_date", sa.Date(), nullable=True),
        sa.Column("ad_count_today", sa.Integer(), nullable=True),
        sa.Column("last_lottery_date", sa.Date(), nullable=True),
        sa.Column("lottery_count_today", sa.Integer(), nullable=True),
        sa.Column("last_mission_date", sa.Date(), nullable=True),
        sa.Column("daily_trade_count", sa.Integer(), nullable=True),
        sa.Column("mission_completed", sa.Integer(), nullable=True),
        sa.Column("updown_active", sa.Integer(), nullable=True),
        sa.Column("updown_bet", sa.BigInteger(), nullable=True),
        sa.Column("updown_current_number", sa.Integer(), nullable=True),
        sa.Column("updown_round", sa.Integer(), nullable=True),
        sa.Column("updown_multiplier", sa.Float(), nullable=True),
        sa.Column("pending_quiz", sa.String(length=2000), nullable=True),
        sa.Column("pending_quiz_bet", sa.BigInteger(), nullable=True),
        sa.Column("enhance_level", sa.Integer(), nullable=True),
        sa.Column("enhance_title_seed", sa.Integer(), nullable=True),
        sa.Column("enhance_class", sa.Integer(), nullable=True),
        sa.Column("achievements", sa.String(length=1000), nullable=True),
        sa.Column("total_profit_realized", sa.BigInteger(), nullable=True),
        sa.Column("total_trades", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("kakao_id"),
    )
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_users_kakao_id"), ["kakao_id"], unique=False
        )


def _create_weekly_challenges() -> None:
    op.create_table(
        "weekly_challenges",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("week_id", sa.String(length=20), nullable=False),
        sa.Column("challenge_type", sa.String(length=50), nullable=False),
        sa.Column("target_value", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("reward", sa.BigInteger(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("week_id"),
    )


def _create_asset_history() -> None:
    op.create_table(
        "asset_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("kakao_id", sa.String(length=100), nullable=False),
        sa.Column("record_date", sa.Date(), nullable=False),
        sa.Column("total_asset", sa.BigInteger(), nullable=False),
        sa.Column("cash", sa.BigInteger(), nullable=False),
        sa.Column("stock_value", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["kakao_id"],
            ["users.kakao_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kakao_id", "record_date", name="unique_user_date_asset"),
    )
    with op.batch_alter_table("asset_history", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_asset_history_kakao_id"), ["kakao_id"], unique=False
        )


def _create_battles() -> None:
    op.create_table(
        "battles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("challenger_id", sa.String(length=100), nullable=False),
        sa.Column("opponent_id", sa.String(length=100), nullable=True),
        sa.Column("stock_code", sa.String(length=20), nullable=False),
        sa.Column("stock_name", sa.String(length=100), nullable=False),
        sa.Column("start_price", sa.Integer(), nullable=True),
        sa.Column("bet_amount", sa.BigInteger(), nullable=True),
        sa.Column("challenger_prediction", sa.String(length=10), nullable=False),
        sa.Column("opponent_prediction", sa.String(length=10), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("end_price", sa.Integer(), nullable=True),
        sa.Column("winner_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["challenger_id"],
            ["users.kakao_id"],
        ),
        sa.ForeignKeyConstraint(
            ["opponent_id"],
            ["users.kakao_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("battles", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_battles_challenger_id"), ["challenger_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_battles_opponent_id"), ["opponent_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_battles_status"), ["status"], unique=False)


def _create_chatroom_members() -> None:
    op.create_table(
        "chatroom_members",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("group_key", sa.String(length=200), nullable=False),
        sa.Column("kakao_id", sa.String(length=100), nullable=False),
        sa.Column("last_active", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["kakao_id"],
            ["users.kakao_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_key", "kakao_id", name="unique_chatroom_member"),
    )
    with op.batch_alter_table("chatroom_members", schema=None) as batch_op:
        batch_op.create_index(
            "ix_chatroom_group_kakao", ["group_key", "kakao_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_chatroom_members_group_key"), ["group_key"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_chatroom_members_kakao_id"), ["kakao_id"], unique=False
        )


def _create_holdings() -> None:
    op.create_table(
        "holdings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("kakao_id", sa.String(length=100), nullable=False),
        sa.Column("stock_code", sa.String(length=20), nullable=False),
        sa.Column("stock_name", sa.String(length=100), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("avg_price", sa.BigInteger(), nullable=True),
        sa.Column("total_invested", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["kakao_id"],
            ["users.kakao_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kakao_id", "stock_code", name="unique_user_stock"),
    )
    with op.batch_alter_table("holdings", schema=None) as batch_op:
        batch_op.create_index(
            "ix_holding_user_stock", ["kakao_id", "stock_code"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_holdings_kakao_id"), ["kakao_id"], unique=False
        )


def _create_milestones() -> None:
    op.create_table(
        "milestones",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("kakao_id", sa.String(length=100), nullable=False),
        sa.Column("milestone_type", sa.String(length=50), nullable=False),
        sa.Column("asset_at_achievement", sa.BigInteger(), nullable=True),
        sa.Column("achieved_at", sa.DateTime(), nullable=True),
        sa.Column("reward_claimed", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["kakao_id"],
            ["users.kakao_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kakao_id", "milestone_type", name="unique_user_milestone"),
    )
    with op.batch_alter_table("milestones", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_milestones_kakao_id"), ["kakao_id"], unique=False
        )


def _create_transactions() -> None:
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("kakao_id", sa.String(length=100), nullable=False),
        sa.Column("stock_code", sa.String(length=20), nullable=False),
        sa.Column("stock_name", sa.String(length=100), nullable=False),
        sa.Column("trade_type", sa.String(length=10), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("total_amount", sa.BigInteger(), nullable=False),
        sa.Column("fee", sa.BigInteger(), nullable=True),
        sa.Column("profit", sa.BigInteger(), nullable=True),
        sa.Column("profit_rate", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["kakao_id"],
            ["users.kakao_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.create_index(
            "ix_transaction_user_created", ["kakao_id", "created_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_transactions_kakao_id"), ["kakao_id"], unique=False
        )


def _create_user_challenges() -> None:
    op.create_table(
        "user_challenges",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("kakao_id", sa.String(length=100), nullable=False),
        sa.Column("challenge_id", sa.Integer(), nullable=False),
        sa.Column("current_value", sa.Integer(), nullable=True),
        sa.Column("completed", sa.Integer(), nullable=True),
        sa.Column("reward_claimed", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["challenge_id"],
            ["weekly_challenges.id"],
        ),
        sa.ForeignKeyConstraint(
            ["kakao_id"],
            ["users.kakao_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kakao_id", "challenge_id", name="unique_user_challenge"),
    )
    with op.batch_alter_table("user_challenges", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_user_challenges_challenge_id"),
            ["challenge_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_user_challenges_kakao_id"), ["kakao_id"], unique=False
        )


# 생성 순서 (FK 의존성 순서를 그대로 유지한다)
_CREATORS = [
    ("api_tokens", _create_api_tokens),
    ("stock_cache", _create_stock_cache),
    ("users", _create_users),
    ("weekly_challenges", _create_weekly_challenges),
    ("asset_history", _create_asset_history),
    ("battles", _create_battles),
    ("chatroom_members", _create_chatroom_members),
    ("holdings", _create_holdings),
    ("milestones", _create_milestones),
    ("transactions", _create_transactions),
    ("user_challenges", _create_user_challenges),
]


def _add_missing_user_columns(inspector) -> None:
    """오래된 DB에 빠져 있을 수 있는 users 컬럼을 채운다"""
    existing = {col["name"] for col in inspector.get_columns("users")}
    for name, coltype in _USER_COLUMNS:
        if name not in existing:
            op.add_column("users", sa.Column(name, coltype, nullable=True))


def _widen_money_columns(conn, inspector, tables) -> None:
    """int4 → int8 확장 (SQLite는 동적 타입이라 불필요)"""
    if conn.dialect.name != "postgresql":
        return
    for table, column in _WIDEN_TO_BIGINT:
        if table not in tables:
            continue
        columns = {col["name"]: col for col in inspector.get_columns(table)}
        if column not in columns:
            continue
        if "BIGINT" in str(columns[column]["type"]).upper():
            continue
        op.alter_column(table, column, type_=sa.BigInteger())


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = set(inspector.get_table_names())

    for name, creator in _CREATORS:
        if name not in existing:
            creator()

    # users는 방금 만들었으면 이미 최신이고, 기존 DB면 빠진 컬럼만 채워진다
    _add_missing_user_columns(sa.inspect(conn))
    _widen_money_columns(conn, sa.inspect(conn), existing)


def downgrade() -> None:
    """
    baseline은 되돌릴 수 없다.

    이 리비전은 두 가지 역할을 겸한다.
      (1) 새 DB에 전체 스키마를 만든다
      (2) Alembic 이전부터 존재하던 운영 DB의 스키마를 그대로 '채택'한다

    (2)로 적용된 DB에서는 이 리비전이 만든 테이블이 하나도 없다. 그런데
    되돌리기는 users·holdings·transactions를 통째로 DROP하므로, Alembic
    도입 전부터 쌓인 실제 유저 데이터까지 전부 사라진다. 어떤 테이블을
    자신이 만들었는지 리비전이 구분할 수 없기 때문에 안전한 되돌리기가
    애초에 불가능하다.

    그래서 실행 자체를 막는다. 스키마를 정말 비워야 한다면 마이그레이션이
    아니라 의도를 명시한 별도 작업으로 해야 한다.

    이후 리비전(0002 이상) 사이의 downgrade는 정상 동작한다.
    """
    raise RuntimeError(
        "0001_baseline은 downgrade할 수 없습니다: "
        "기존 운영 스키마를 채택했을 수 있어 되돌리면 실제 유저 데이터가 삭제됩니다. "
        "0002 이후 리비전 간 downgrade만 사용하세요."
    )
