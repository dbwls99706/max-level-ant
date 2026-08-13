"""
Alembic 실행 환경

DB URL은 alembic.ini가 아니라 settings.DATABASE_URL(환경변수)에서 읽는다.
운영·로컬·CI가 애플리케이션과 같은 설정 경로를 쓰게 해서, 마이그레이션이
앱과 다른 DB를 건드리는 사고를 막는다.
"""

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# 프로젝트 루트를 import 경로에 추가 (models/database를 읽어야 한다)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Base  # noqa: E402
import models  # noqa: F401,E402  (Base.metadata에 모든 테이블 등록)
from settings import DATABASE_URL  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# autogenerate가 비교 대상으로 삼을 모델 메타데이터
target_metadata = Base.metadata


def _database_url() -> str:
    """
    사용할 DB URL.

    우선순위: alembic -x db_url=... > 환경변수 DATABASE_URL
    (-x는 테스트에서 임시 DB를 지정할 때 쓴다)
    """
    override = context.get_x_argument(as_dictionary=True).get("db_url")
    return override or DATABASE_URL


def run_migrations_offline() -> None:
    """SQL 스크립트만 출력 (DB에 연결하지 않음)"""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """실제 DB에 연결해 마이그레이션 실행"""
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            # SQLite는 ALTER를 거의 지원하지 않으므로 배치 모드로 처리한다
            render_as_batch=connection.dialect.name == "sqlite",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
