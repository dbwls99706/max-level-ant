"""
pytest 공통 픽스처
- 인메모리 SQLite DB (테스트용)
- 테스트 유저 생성 헬퍼
"""

import sys
import os
import pytest

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, User
from game_config import GameConfig


# ===========================================
# 인메모리 SQLite 테스트 DB
# ===========================================
TEST_DB_URL = "sqlite:///:memory:"


@pytest.fixture(autouse=True)
def clear_ranking_cache():
    """랭킹 캐시를 테스트마다 비운다.

    RankingService._ranking_cache는 클래스 변수(TTL 5분)라 테스트 사이에
    그대로 남는다. 앞 테스트가 채워둔 랭킹을 뒤 테스트가 읽으면, 방금
    만든 유저가 랭킹에 없어서 '혼자 돌리면 통과, 전체로 돌리면 실패'하는
    테스트가 된다. 원인을 찾기 가장 어려운 종류의 실패다.
    """
    from services.ranking_service import RankingService

    RankingService._ranking_cache.clear()
    yield
    RankingService._ranking_cache.clear()


@pytest.fixture(scope="function")
def db():
    """각 테스트마다 깨끗한 인메모리 DB 제공"""
    engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()

    yield session

    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def test_user(db):
    """기본 테스트 유저 생성"""
    user = User(
        kakao_id="test_user_1234",
        nickname="테스터",
        cash=GameConfig.INITIAL_CASH,
        initial_cash=GameConfig.INITIAL_CASH,
        attendance_streak=0,
        ad_count_today=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def rich_user(db):
    """고액 보유 테스트 유저"""
    user = User(
        kakao_id="rich_user_9999",
        nickname="부자",
        cash=100_000_000,
        initial_cash=GameConfig.INITIAL_CASH,
        attendance_streak=0,
        ad_count_today=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def poor_user(db):
    """잔고 부족 테스트 유저"""
    user = User(
        kakao_id="poor_user_0001",
        nickname="가난한자",
        cash=1000,  # 1,000원
        initial_cash=GameConfig.INITIAL_CASH,
        attendance_streak=0,
        ad_count_today=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def skill_key(monkeypatch):
    """
    /skill 인증 키를 설정하고 요청에 붙일 헤더를 돌려준다.

    TestClient를 띄우기 전에 써야 한다. 키가 없으면 운영 모드 기동 가드에
    걸려 앱이 뜨지 않는다.
    """
    from security import SecurityConfig

    key = "test-skill-key"
    monkeypatch.setattr(SecurityConfig, "SKILL_API_KEY", key)
    monkeypatch.setattr(SecurityConfig, "SKILL_API_KEY_HEADER", "X-Skill-Key")
    monkeypatch.setattr(SecurityConfig, "DEV_MODE", False)
    return {"X-Skill-Key": key}
