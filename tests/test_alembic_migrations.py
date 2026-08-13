"""
Alembic 마이그레이션 테스트

이 프로젝트는 Alembic 이전에 `Base.metadata.create_all()` +
`database._migrate_db()`로 스키마를 관리했다. 그래서 운영 DB에는 이미
테이블이 존재하고, baseline 리비전이 그걸 다시 만들려 들면 배포가 깨진다.

검증:
  - 새 DB: `upgrade head`가 전체 스키마를 만든다
  - 기존 DB: 같은 명령이 데이터를 지우지 않고 통과한다 (멱등)
  - 오래된 DB: 빠진 테이블·컬럼만 채우고 int4 금액 컬럼을 int8로 넓힌다
  - 마이그레이션 결과가 models.py와 정확히 일치한다 (autogenerate 차이 없음)
  - baseline이 Base.metadata를 참조하지 않는다
    (참조하면 모델이 바뀔 때 과거 리비전이 미래 스키마를 만들어버린다)
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASELINE = PROJECT_ROOT / "migrations" / "versions" / "0001_baseline_baseline_schema.py"

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")


def _alembic(db_url: str, *args) -> subprocess.CompletedProcess:
    """alembic CLI를 별도 프로세스로 실행 (env.py가 DATABASE_URL을 읽는다)"""
    env = dict(os.environ, DATABASE_URL=db_url)
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def _expected_tables() -> set:
    from models import Base

    return set(Base.metadata.tables)


# ===========================================
# 스크립트 자체에 대한 검사 (DB 불필요)
# ===========================================
class TestBaselineScript:
    def test_baseline_does_not_import_app_models(self):
        """
        baseline은 '그 시점의' 스키마로 고정돼야 한다. models/database를
        import해 Base.metadata를 쓰면 모델이 바뀔 때 과거 리비전이 미래
        스키마를 만들어버리고, 이후 리비전과 충돌한다.

        (주석·docstring이 아니라 실제 import 문만 본다)
        """
        import ast

        tree = ast.parse(BASELINE.read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])

        forbidden = imported & {"models", "database"}
        assert not forbidden, (
            f"baseline이 앱 모듈을 import한다: {forbidden} — 리비전이 고정되지 않는다"
        )

    def test_baseline_creates_every_model_table(self):
        """모델의 모든 테이블이 baseline에 들어 있어야 한다"""
        source = BASELINE.read_text()
        for table in _expected_tables():
            assert f'"{table}"' in source, f"baseline에 {table} 테이블이 없다"

    def test_single_head_revision(self):
        """head가 여러 개면 `upgrade head`가 실패한다"""
        result = _alembic("sqlite:///:memory:", "heads")
        assert result.returncode == 0, result.stderr
        heads = [ln for ln in result.stdout.splitlines() if "(head)" in ln]
        assert len(heads) == 1, f"head가 {len(heads)}개다:\n{result.stdout}"


# ===========================================
# SQLite 경로
# ===========================================
class TestSqliteUpgrade:
    def test_fresh_database_gets_full_schema(self, tmp_path):
        db_file = tmp_path / "fresh.db"
        url = f"sqlite:///{db_file}"

        result = _alembic(url, "upgrade", "head")
        assert result.returncode == 0, result.stderr

        engine = create_engine(url)
        tables = set(inspect(engine).get_table_names())
        engine.dispose()

        missing = _expected_tables() - tables
        assert not missing, f"생성되지 않은 테이블: {missing}"
        assert "alembic_version" in tables

    def test_upgrade_on_existing_schema_preserves_data(self, tmp_path):
        """
        Alembic 이전 방식으로 만들어진 DB에 그대로 upgrade해도
        테이블을 다시 만들지 않고 데이터도 남아 있어야 한다.
        """
        from models import Base

        db_file = tmp_path / "legacy.db"
        url = f"sqlite:///{db_file}"

        engine = create_engine(url)
        Base.metadata.create_all(engine)
        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO users (kakao_id, nickname, cash, initial_cash) "
                    "VALUES ('keep-me', '기존유저', 12345, 10000000)"
                )
            )
            conn.commit()
        engine.dispose()

        result = _alembic(url, "upgrade", "head")
        assert result.returncode == 0, (
            f"기존 스키마 위에서 마이그레이션이 실패했다:\n{result.stderr}"
        )

        engine = create_engine(url)
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT cash FROM users WHERE kakao_id = 'keep-me'")
            ).fetchone()
            version = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar()
        engine.dispose()

        assert row is not None, "기존 데이터가 사라졌다"
        assert row[0] == 12345
        assert version == "0001_baseline"

    def test_upgrade_is_repeatable(self, tmp_path):
        """두 번 돌려도 실패하지 않는다"""
        url = f"sqlite:///{tmp_path / 'twice.db'}"
        assert _alembic(url, "upgrade", "head").returncode == 0
        second = _alembic(url, "upgrade", "head")
        assert second.returncode == 0, second.stderr


# ===========================================
# PostgreSQL 경로 (운영 dialect)
# ===========================================
@pytest.mark.postgres
@pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL 미설정 - PostgreSQL 마이그레이션 테스트 건너뜀",
)
class TestPostgresUpgrade:
    @pytest.fixture
    def clean_pg(self):
        """스키마를 비운 상태에서 시작한다"""
        engine = create_engine(TEST_DATABASE_URL)
        with engine.connect() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
            conn.commit()
        yield engine
        engine.dispose()

    def test_fresh_upgrade_matches_models_exactly(self, clean_pg):
        """
        `alembic check`은 모델과 실제 스키마의 차이를 잡는다.
        차이가 있으면 baseline이 models.py를 정확히 재현하지 못한 것이다.
        """
        assert _alembic(TEST_DATABASE_URL, "upgrade", "head").returncode == 0

        check = _alembic(TEST_DATABASE_URL, "check")
        assert check.returncode == 0, (
            f"마이그레이션 결과가 models.py와 다르다:\n{check.stdout}\n{check.stderr}"
        )

    def test_legacy_database_converges_without_data_loss(self, clean_pg):
        """
        오래된 운영 DB 재현: 테이블 하나 없음 + users 컬럼 몇 개 없음 +
        금액 컬럼이 int4. upgrade가 빠진 것만 채우고 데이터는 지키는지 본다.
        """
        from models import Base

        engine = clean_pg
        Base.metadata.create_all(engine)

        with engine.connect() as conn:
            conn.execute(text("DROP TABLE api_tokens"))
            conn.execute(
                text(
                    "ALTER TABLE users "
                    "DROP COLUMN enhance_class, "
                    "DROP COLUMN pending_quiz, "
                    "DROP COLUMN total_trades"
                )
            )
            conn.execute(text("ALTER TABLE transactions ALTER COLUMN fee TYPE INTEGER"))
            conn.execute(
                text("ALTER TABLE holdings ALTER COLUMN avg_price TYPE INTEGER")
            )
            conn.execute(
                text(
                    "INSERT INTO users (kakao_id, nickname, cash, initial_cash) "
                    "VALUES ('legacy-user', '기존유저', 777, 10000000)"
                )
            )
            conn.commit()

        result = _alembic(TEST_DATABASE_URL, "upgrade", "head")
        assert result.returncode == 0, (
            f"오래된 스키마 위에서 마이그레이션이 실패했다:\n{result.stderr}"
        )

        inspector = inspect(engine)
        assert "api_tokens" in inspector.get_table_names(), (
            "빠진 테이블이 복구되지 않았다"
        )

        user_columns = {c["name"] for c in inspector.get_columns("users")}
        for col in ("enhance_class", "pending_quiz", "total_trades"):
            assert col in user_columns, f"빠진 컬럼이 복구되지 않았다: {col}"

        fee_type = {c["name"]: c for c in inspector.get_columns("transactions")}["fee"]
        assert "BIGINT" in str(fee_type["type"]).upper(), (
            "int4 금액 컬럼이 int8로 넓혀지지 않았다"
        )

        with engine.connect() as conn:
            cash = conn.execute(
                text("SELECT cash FROM users WHERE kakao_id = 'legacy-user'")
            ).scalar()
        assert cash == 777, "기존 데이터가 사라졌다"

        check = _alembic(TEST_DATABASE_URL, "check")
        assert check.returncode == 0, (
            f"수렴 후에도 models.py와 다르다:\n{check.stdout}\n{check.stderr}"
        )
