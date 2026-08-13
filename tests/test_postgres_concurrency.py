"""
PostgreSQL 동시성 통합 테스트

거래/보상 정합성은 `SELECT ... FOR UPDATE` row lock에 의존한다.
그런데 나머지 테스트는 in-memory SQLite를 쓰므로 PostgreSQL의
row-level lock 동작을 검증하지 못한다.

이 파일은 실제 PostgreSQL에 붙어서 다음을 검증한다.
  - 동시 매수가 잔액을 초과 지출하지 않는다 (double-spend)
  - 동시 출석이 보상을 한 번만 지급한다
  - 동시 보물상자가 일일 횟수 제한을 넘지 않는다

실행:
    TEST_DATABASE_URL=postgresql://user:pw@localhost/dbname pytest -m postgres
환경변수가 없으면 전체 skip한다.
"""

import os
import threading

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from game_config import GameConfig
from models import Base, Holding, User

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not TEST_DATABASE_URL,
        reason="TEST_DATABASE_URL 미설정 - PostgreSQL 통합 테스트 건너뜀",
    ),
]


@pytest.fixture(scope="module")
def pg_engine():
    engine = create_engine(TEST_DATABASE_URL, pool_size=10, max_overflow=10)
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def pg_sessionmaker(pg_engine):
    """테이블을 비우고 세션 팩토리를 준다"""
    with pg_engine.begin() as conn:
        tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    return sessionmaker(bind=pg_engine, autocommit=False, autoflush=False)


def _make_user(factory, kakao_id: str, cash: int) -> None:
    db = factory()
    try:
        db.add(
            User(
                kakao_id=kakao_id,
                nickname="동시성테스터",
                cash=cash,
                initial_cash=cash,
            )
        )
        db.commit()
    finally:
        db.close()


def _run_concurrently(fn, count: int):
    """count개 스레드를 동시에 출발시키고 결과를 모은다"""
    barrier = threading.Barrier(count)
    results = []
    lock = threading.Lock()

    def worker(index):
        barrier.wait()
        try:
            outcome = fn(index)
        except Exception as e:  # 실패도 결과로 남긴다
            outcome = e
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results


def _make_holding(factory, kakao_id: str, code: str, name: str) -> None:
    """
    보유 종목을 미리 만들어 둔다.

    첫 매수는 holdings에 INSERT하므로 UNIQUE(kakao_id, stock_code) 제약이
    동시 요청을 대신 걸러버린다. 그러면 row lock이 없어도 테스트가 통과해
    검출력이 사라진다. 보유분을 미리 만들어 UPDATE 경로로 태워야
    잔액 정합성(row lock) 자체를 검증할 수 있다.
    """
    db = factory()
    try:
        db.add(
            Holding(
                kakao_id=kakao_id,
                stock_code=code,
                stock_name=name,
                quantity=1,
                avg_price=1,
                total_invested=1,
            )
        )
        db.commit()
    finally:
        db.close()


class TestConcurrentBuyDoesNotOverspend:
    def test_concurrent_buys_cannot_exceed_balance(self, pg_sessionmaker, monkeypatch):
        """
        잔액 100만원인 유저가 80만원어치 매수를 동시에 보내면
        하나만 성공해야 한다 (row lock이 없으면 여러 건이 통과해 초과 지출된다).
        """
        from services import trade_service
        from services.trade_service import TradeService

        kakao_id = "concurrent_buyer"
        cash = 1_000_000
        price = 100_000
        quantity = 8  # 80만원어치

        _make_user(pg_sessionmaker, kakao_id, cash)
        _make_holding(pg_sessionmaker, kakao_id, "005930", "삼성전자")

        # 시세/장 상태는 고정 (외부 API·시간 의존 제거)
        monkeypatch.setattr(
            trade_service.StockService,
            "get_price",
            classmethod(
                lambda cls, q: {"code": "005930", "name": "삼성전자", "price": price}
            ),
        )
        monkeypatch.setattr(trade_service, "is_trading_available", lambda: True)

        def buy(_index):
            db = pg_sessionmaker()
            try:
                return TradeService.buy_stock(db, kakao_id, "삼성전자", quantity)
            finally:
                db.close()

        results = _run_concurrently(buy, 6)
        succeeded = [r for r in results if isinstance(r, dict) and r.get("success")]

        db = pg_sessionmaker()
        try:
            user = db.query(User).filter(User.kakao_id == kakao_id).one()
            final_cash = user.cash
        finally:
            db.close()

        assert len(succeeded) == 1, (
            f"동시 매수 {len(succeeded)}건 성공 — 잔액을 초과 지출했다 "
            f"(최종 잔액 {final_cash:,})"
        )
        assert final_cash >= 0, f"잔액이 음수가 됐다: {final_cash:,}"

    def test_many_buys_never_drive_balance_negative(self, pg_sessionmaker, monkeypatch):
        """8개를 동시에 던져도 잔액은 음수가 되지 않는다"""
        from services import trade_service
        from services.trade_service import TradeService

        kakao_id = "concurrent_buyer_many"
        cash = 1_000_000
        price = 100_000

        _make_user(pg_sessionmaker, kakao_id, cash)
        _make_holding(pg_sessionmaker, kakao_id, "005930", "삼성전자")
        monkeypatch.setattr(
            trade_service.StockService,
            "get_price",
            classmethod(
                lambda cls, q: {"code": "005930", "name": "삼성전자", "price": price}
            ),
        )
        monkeypatch.setattr(trade_service, "is_trading_available", lambda: True)

        def buy(_index):
            db = pg_sessionmaker()
            try:
                return TradeService.buy_stock(db, kakao_id, "삼성전자", 3)
            finally:
                db.close()

        results = _run_concurrently(buy, 8)
        succeeded = [r for r in results if isinstance(r, dict) and r.get("success")]

        db = pg_sessionmaker()
        try:
            user = db.query(User).filter(User.kakao_id == kakao_id).one()
            assert succeeded, "매수가 한 번도 성공하지 않았다 (테스트가 무의미)"
            assert user.cash >= 0, f"잔액이 음수가 됐다: {user.cash:,}"
            # 수수료를 감안해도 지출은 보유 현금을 넘을 수 없다
            assert user.cash <= cash
        finally:
            db.close()


class TestConcurrentAttendance:
    def test_reward_is_granted_only_once(self, pg_sessionmaker):
        """동시에 /출석을 여러 번 보내도 보상은 하루 한 번만 지급돼야 한다"""
        from services.user_service import UserService

        kakao_id = "concurrent_attender"
        cash = 1_000_000
        _make_user(pg_sessionmaker, kakao_id, cash)

        def attend(_index):
            db = pg_sessionmaker()
            try:
                return UserService.check_attendance(db, kakao_id)
            finally:
                db.close()

        # check_attendance는 (success, reward, streak, cash, enhance_level) 튜플을 반환한다
        results = _run_concurrently(attend, 6)
        granted = [r for r in results if isinstance(r, tuple) and r[0] is True]

        db = pg_sessionmaker()
        try:
            user = db.query(User).filter(User.kakao_id == kakao_id).one()
            gained = user.cash - cash
        finally:
            db.close()

        assert len(granted) == 1, f"출석 보상이 {len(granted)}회 지급됐다"
        # 실제 지급액도 1회분이어야 한다 (각성 레벨 0이므로 배율 1.0)
        assert gained == GameConfig.ATTENDANCE_REWARD, (
            f"보상 지급액이 1회분이 아니다 (증가액 {gained:,})"
        )


class TestConcurrentLottery:
    def test_daily_limit_is_not_exceeded(self, pg_sessionmaker):
        """보물상자를 동시에 던져도 일일 한도를 넘지 않아야 한다"""
        from services.game_service import GameService

        kakao_id = "concurrent_lottery"
        _make_user(pg_sessionmaker, kakao_id, 1_000_000)

        attempts = GameConfig.MAX_LOTTERY_PER_DAY + 5

        def play(_index):
            db = pg_sessionmaker()
            try:
                return GameService.play_lottery(db, kakao_id)
            finally:
                db.close()

        results = _run_concurrently(play, attempts)
        succeeded = [
            r for r in results if isinstance(r, dict) and r.get("success") is True
        ]

        # 상한만 보면 전부 실패해도 통과하므로 하한도 함께 확인한다
        assert succeeded, "보물상자가 한 번도 성공하지 않았다 (테스트가 무의미)"
        assert len(succeeded) <= GameConfig.MAX_LOTTERY_PER_DAY, (
            f"보물상자가 일일 한도({GameConfig.MAX_LOTTERY_PER_DAY})를 넘어 "
            f"{len(succeeded)}회 성공했다"
        )
