"""
데이터베이스 연결 및 세션 관리
"""
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError
from config import DATABASE_URL
from utils import get_handler_logger

logger = get_handler_logger()

# SQLite를 사용할 경우 check_same_thread 옵션 필요
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

# 엔진 생성
engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,  # 연결 상태 확인
    echo=False  # SQL 로그 출력 (디버깅 시 True)
)

# 세션 팩토리
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

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


def init_db():
    """
    데이터베이스 테이블 생성 및 마이그레이션
    앱 시작 시 호출
    """
    # 모든 모델 임포트 (테이블 생성을 위해)
    from models import (
        User, Holding, Transaction,
        Battle, WeeklyChallenge, UserChallenge,
        Milestone, AssetHistory, StockCache
    )

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
    if 'users' not in inspector.get_table_names():
        return

    # 현재 users 테이블의 컬럼 목록
    existing_columns = {col['name'] for col in inspector.get_columns('users')}

    # 추가해야 할 컬럼들 정의 (컬럼명: SQL 타입 및 기본값)
    new_columns = {
        'last_mission_date': 'DATE',
        'daily_trade_count': 'INTEGER DEFAULT 0',
        'mission_completed': 'INTEGER DEFAULT 0',
        'achievements': "VARCHAR(1000) DEFAULT '[]'",
        'total_profit_realized': 'BIGINT DEFAULT 0',
        'total_trades': 'INTEGER DEFAULT 0',
        'last_lottery_date': 'DATE',
        'lottery_count_today': 'INTEGER DEFAULT 0',
        'nickname_change_count': 'INTEGER DEFAULT 0',
        'last_nickname_change': 'DATE',
    }

    added_count = 0
    with engine.connect() as conn:
        for col_name, col_type in new_columns.items():
            if col_name not in existing_columns:
                try:
                    sql = f'ALTER TABLE users ADD COLUMN {col_name} {col_type}'
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


def reset_db():
    """
    데이터베이스 초기화 (모든 데이터 삭제)
    주의: 모든 유저 데이터가 삭제됩니다!
    """
    from models import User, Holding, Transaction

    # 모든 테이블 삭제
    Base.metadata.drop_all(bind=engine)
    logger.warning("모든 테이블 삭제됨")

    # 테이블 재생성
    Base.metadata.create_all(bind=engine)
    logger.info("테이블 재생성 완료")

    return True
