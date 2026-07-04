"""
데이터베이스 연결 및 세션 관리
"""

import re
from datetime import datetime, timezone
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError
from config import DATABASE_URL
from utils import get_handler_logger

logger = get_handler_logger()

# SQLite를 사용할 경우 check_same_thread 옵션 필요
connect_args = {}
is_sqlite = DATABASE_URL.startswith("sqlite")
if is_sqlite:
    connect_args = {"check_same_thread": False}

# 엔진 생성 (PostgreSQL용 커넥션 풀 설정 포함)
engine_kwargs = {
    "connect_args": connect_args,
    "pool_pre_ping": True,  # 연결 상태 확인 (끊긴 연결 자동 재연결)
    "echo": False,  # SQL 로그 출력 (디버깅 시 True)
}

# PostgreSQL인 경우 커넥션 풀 설정 추가
if not is_sqlite:
    engine_kwargs.update(
        {
            "pool_size": 5,  # 기본 연결 수
            "max_overflow": 10,  # 추가 연결 허용 수 (최대 15개)
            "pool_recycle": 1800,  # 30분마다 연결 갱신 (DB timeout 방지)
            "pool_timeout": 30,  # 연결 대기 최대 시간 (초)
        }
    )

engine = create_engine(DATABASE_URL, **engine_kwargs)

# 세션 팩토리
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base 클래스
Base = declarative_base()


def get_db():
    """
    데이터베이스 세션 생성기
    FastAPI Depends에서 사용
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_health() -> bool:
    """
    데이터베이스 연결 상태 확인
    헬스체크용
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError as e:
        logger.error(f"DB 헬스체크 실패: {e}")
        return False


def init_db():
    """
    데이터베이스 테이블 생성 및 마이그레이션
    앱 시작 시 호출
    """
    # 모든 모델 임포트 (Base.metadata에 테이블 등록 — 임포트 순서와 무관하게 동작 보장)
    import models  # noqa: F401

    # 테이블 생성
    Base.metadata.create_all(bind=engine)
    logger.info("데이터베이스 테이블 생성 완료")

    # 기존 테이블에 누락된 컬럼 추가 (마이그레이션)
    _migrate_db()


def _migrate_db():
    """
    기존 테이블에 새 컬럼 추가
    """
    inspector = inspect(engine)

    # users 테이블이 존재하는지 확인
    if "users" not in inspector.get_table_names():
        return

    # 현재 users 테이블의 컬럼 목록
    existing_columns = {col["name"] for col in inspector.get_columns("users")}

    # 추가해야 할 컬럼들 정의 (컬럼명: SQL 타입 및 기본값)
    new_columns = {
        "last_mission_date": "DATE",
        "daily_trade_count": "INTEGER DEFAULT 0",
        "mission_completed": "INTEGER DEFAULT 0",
        "achievements": "VARCHAR(1000) DEFAULT '[]'",
        "total_profit_realized": "BIGINT DEFAULT 0",
        "total_trades": "INTEGER DEFAULT 0",
        "last_lottery_date": "DATE",
        "lottery_count_today": "INTEGER DEFAULT 0",
        "nickname_change_count": "INTEGER DEFAULT 0",
        "last_nickname_change": "DATE",
        "updown_active": "INTEGER DEFAULT 0",
        "updown_bet": "BIGINT DEFAULT 0",
        "updown_current_number": "INTEGER DEFAULT 0",
        "updown_round": "INTEGER DEFAULT 0",
        "updown_multiplier": "FLOAT DEFAULT 1.0",
        "enhance_level": "INTEGER DEFAULT 0",
        "enhance_title_seed": "INTEGER DEFAULT 0",
        "enhance_class": "INTEGER DEFAULT 0",
        "pending_quiz": "VARCHAR(2000)",
        "pending_quiz_bet": "BIGINT DEFAULT 0",
    }

    # 허용된 SQL 타입 화이트리스트 (SQL 인젝션 방지)
    _VALID_COL_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")
    _ALLOWED_COL_TYPES = {
        "INTEGER",
        "BIGINT",
        "VARCHAR",
        "TEXT",
        "DATE",
        "BOOLEAN",
        "FLOAT",
        "REAL",
        "INTEGER DEFAULT 0",
        "BIGINT DEFAULT 0",
        "INTEGER DEFAULT 1",
        "FLOAT DEFAULT 1.0",
        "VARCHAR(1000) DEFAULT '[]'",
        "DATE",
        "BOOLEAN DEFAULT FALSE",
        "BOOLEAN DEFAULT TRUE",
    }

    def _is_safe_col_type(col_type: str) -> bool:
        """col_type이 안전한 SQL 타입인지 확인 (화이트리스트 + 패턴 검사)"""
        if col_type in _ALLOWED_COL_TYPES:
            return True
        # INTEGER DEFAULT N, BIGINT DEFAULT N 패턴 허용
        import re as _re

        return bool(
            _re.match(
                r"^(INTEGER|BIGINT|VARCHAR\(\d+\)|TEXT|DATE|BOOLEAN|FLOAT|REAL)"
                r"(\s+DEFAULT\s+(\d+|\'[^\']*\'|TRUE|FALSE|NULL))?$",
                col_type,
                _re.IGNORECASE,
            )
        )

    added_count = 0
    with engine.connect() as conn:
        for col_name, col_type in new_columns.items():
            if col_name not in existing_columns:
                # 컬럼명 유효성 검증
                if not _VALID_COL_NAME.match(col_name):
                    logger.error(f"유효하지 않은 컬럼명 건너뜀: {col_name}")
                    continue
                # 컬럼 타입 유효성 검증 (SQL 인젝션 방지 - 화이트리스트)
                if not _is_safe_col_type(col_type):
                    logger.error(
                        f"유효하지 않은 컬럼 타입 건너뜀: {col_name} {col_type}"
                    )
                    continue
                try:
                    sql = f"ALTER TABLE users ADD COLUMN {col_name} {col_type}"
                    conn.execute(text(sql))
                    conn.commit()
                    logger.info(f"컬럼 추가됨: users.{col_name}")
                    added_count += 1
                except SQLAlchemyError as e:
                    logger.warning(f"컬럼 추가 실패 ({col_name}): {e}")

    if added_count > 0:
        logger.info(f"데이터베이스 마이그레이션 완료 ({added_count}개 컬럼 추가)")
    else:
        logger.debug("마이그레이션: 추가할 컬럼 없음")

    _widen_integer_columns(inspector)


def _widen_integer_columns(inspector):
    """
    int4 → int8 타입 확장 (대형 거래 시 오버플로 방지)
    - transactions.fee, holdings.avg_price는 거래 금액에 비례해 int4 상한을 넘을 수 있음
    - SQLite는 동적 타입이라 확장 불필요
    """
    if engine.dialect.name != "postgresql":
        return

    type_upgrades = [
        ("transactions", "fee"),
        ("holdings", "avg_price"),
    ]
    table_names = set(inspector.get_table_names())

    with engine.connect() as conn:
        for table, column in type_upgrades:
            if table not in table_names:
                continue
            columns = {col["name"]: col for col in inspector.get_columns(table)}
            if column not in columns:
                continue
            if "BIGINT" in str(columns[column]["type"]).upper():
                continue
            try:
                conn.execute(
                    text(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE BIGINT")
                )
                conn.commit()
                logger.info(f"컬럼 타입 확장됨: {table}.{column} → BIGINT")
            except SQLAlchemyError as e:
                logger.warning(f"컬럼 타입 확장 실패 ({table}.{column}): {e}")


def reset_db():
    """
    데이터베이스 초기화 (모든 데이터 삭제)
    주의: 모든 유저 데이터가 삭제됩니다!
    """

    # 모든 테이블 삭제
    Base.metadata.drop_all(bind=engine)
    logger.warning("모든 테이블 삭제됨")

    # 테이블 재생성
    Base.metadata.create_all(bind=engine)
    logger.info("테이블 재생성 완료")

    return True


def cleanup_old_records(
    transaction_days: int = 90, asset_history_days: int = 365
) -> dict:
    """
    오래된 레코드 정리 (데이터베이스 용량 관리)

    Args:
        transaction_days: 거래 내역 보존 기간 (기본 90일)
        asset_history_days: 자산 히스토리 보존 기간 (기본 365일)

    Returns:
        삭제된 레코드 수 정보
    """
    from datetime import timedelta
    from models import Transaction, AssetHistory

    result = {"transactions": 0, "asset_history": 0}
    db = None

    try:
        db = SessionLocal()

        # 오래된 거래 내역 삭제
        transaction_cutoff = datetime.now(timezone.utc).replace(
            tzinfo=None
        ) - timedelta(days=transaction_days)
        deleted_transactions = (
            db.query(Transaction)
            .filter(Transaction.created_at < transaction_cutoff)
            .delete(synchronize_session=False)
        )
        result["transactions"] = deleted_transactions

        # 오래된 자산 히스토리 삭제
        asset_cutoff = (
            datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(days=asset_history_days)
        ).date()
        deleted_history = (
            db.query(AssetHistory)
            .filter(AssetHistory.record_date < asset_cutoff)
            .delete(synchronize_session=False)
        )
        result["asset_history"] = deleted_history

        db.commit()

        if deleted_transactions > 0 or deleted_history > 0:
            logger.info(
                f"DB 정리 완료: 거래내역 {deleted_transactions}건, "
                f"자산히스토리 {deleted_history}건 삭제"
            )

    except SQLAlchemyError as e:
        logger.error(f"DB 정리 실패: {e}")
        if db:
            db.rollback()
    finally:
        if db:
            db.close()

    return result
