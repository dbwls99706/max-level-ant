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
import time

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

    # 일부 worker가 살아 있으면 results가 불완전한 채로 단정하게 된다.
    # (예: lock 경합으로 멈춘 스레드의 성공 건수가 집계에서 빠짐)
    alive = [t for t in threads if t.is_alive()]
    assert not alive, f"{len(alive)}개 worker가 30초 안에 종료되지 않음"

    assert len(results) == count, (
        f"결과 {len(results)}건 / 요청 {count}건 — 일부 worker 결과가 누락됐다"
    )
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


class TestLockScope:
    """
    락 보유 구간 검증

    거래는 KIS 시세 조회를 락 밖에서 끝내고, 락을 잡은 뒤 잔고·보유량을
    다시 읽어 검증한다. 이 구조가 유지되는지 실제 PostgreSQL에서 확인한다.
    """

    def test_slow_price_lookup_does_not_hold_row_lock(
        self, pg_sessionmaker, monkeypatch
    ):
        """
        KIS가 느려도 같은 유저의 다른 DB 작업이 row lock에 막히지 않아야 한다.

        예전 구조(FOR UPDATE → KIS → mutation)에서는 시세 조회 1초 동안
        같은 유저 row가 잠겨 다른 요청이 그만큼 대기했다.
        """
        from services import trade_service
        from services.trade_service import TradeService

        kakao_id = "lock_scope_user"
        _make_user(pg_sessionmaker, kakao_id, 1_000_000)
        _make_holding(pg_sessionmaker, kakao_id, "005930", "삼성전자")

        price_delay = 1.0
        in_price_lookup = threading.Event()

        def slow_price(cls, query):
            in_price_lookup.set()
            time.sleep(price_delay)
            return {"code": "005930", "name": "삼성전자", "price": 100_000}

        monkeypatch.setattr(
            trade_service.StockService, "get_price", classmethod(slow_price)
        )
        monkeypatch.setattr(trade_service, "is_trading_available", lambda: True)

        def slow_buy():
            db = pg_sessionmaker()
            try:
                TradeService.buy_stock(db, kakao_id, "삼성전자", 1)
            finally:
                db.close()

        buyer = threading.Thread(target=slow_buy)
        buyer.start()
        assert in_price_lookup.wait(timeout=5), "시세 조회가 시작되지 않았다"

        # 시세 조회가 진행 중인 동안 같은 유저 row를 잠가본다.
        # 락이 시세 조회 밖에 있다면 곧바로 잡힌다.
        time.sleep(0.1)
        started = time.monotonic()
        db = pg_sessionmaker()
        try:
            db.execute(
                text("SELECT 1 FROM users WHERE kakao_id = :kid FOR UPDATE").bindparams(
                    kid=kakao_id
                )
            )
            db.commit()
        finally:
            db.close()
        waited = time.monotonic() - started
        buyer.join(timeout=10)

        assert waited < price_delay / 2, (
            f"시세 조회 중 row lock을 {waited:.2f}초 기다렸다 — "
            f"락이 외부 API 호출을 감싸고 있다"
        )

    def test_cash_change_during_price_lookup_is_revalidated(
        self, pg_sessionmaker, monkeypatch
    ):
        """
        시세 조회 중 잔고가 줄어도, 락 이후 재검증으로 초과 매수를 막아야 한다.

        락 밖에서 읽은 잔고를 그대로 믿으면 TOCTOU가 된다.
        """
        from services import trade_service
        from services.trade_service import TradeService

        kakao_id = "toctou_user"
        _make_user(pg_sessionmaker, kakao_id, 1_000_000)
        _make_holding(pg_sessionmaker, kakao_id, "005930", "삼성전자")

        in_price_lookup = threading.Event()
        cash_drained = threading.Event()

        def slow_price(cls, query):
            in_price_lookup.set()
            cash_drained.wait(timeout=5)  # 잔고가 빠질 때까지 대기
            return {"code": "005930", "name": "삼성전자", "price": 100_000}

        monkeypatch.setattr(
            trade_service.StockService, "get_price", classmethod(slow_price)
        )
        monkeypatch.setattr(trade_service, "is_trading_available", lambda: True)

        result = {}

        def buy():
            db = pg_sessionmaker()
            try:
                result["value"] = TradeService.buy_stock(db, kakao_id, "삼성전자", 8)
            finally:
                db.close()

        buyer = threading.Thread(target=buy)
        buyer.start()
        assert in_price_lookup.wait(timeout=5)

        # 시세 조회 중에 잔고를 비운다
        db = pg_sessionmaker()
        try:
            db.execute(
                text("UPDATE users SET cash = 1000 WHERE kakao_id = :kid").bindparams(
                    kid=kakao_id
                )
            )
            db.commit()
        finally:
            db.close()
        cash_drained.set()
        buyer.join(timeout=10)

        assert result["value"].get("success") is not True, (
            "잔고가 빠졌는데도 매수가 성공했다 — 락 이후 재검증이 없다"
        )

        db = pg_sessionmaker()
        try:
            user = db.query(User).filter(User.kakao_id == kakao_id).one()
            assert user.cash >= 0, f"잔액이 음수가 됐다: {user.cash:,}"
        finally:
            db.close()

    def test_concurrent_buy_max_does_not_overspend(self, pg_sessionmaker, monkeypatch):
        """
        전량 매수를 동시에 보내도 초과 지출하면 안 된다.

        buy_max는 잔고로 수량을 정하므로, 수량 계산이 반드시 락 안에서
        이뤄져야 한다. 락 밖 잔고로 계산하면 여러 요청이 같은 수량을 산정한다.
        """
        from services import trade_service
        from services.trade_service import TradeService

        kakao_id = "buymax_user"
        cash = 1_000_000
        _make_user(pg_sessionmaker, kakao_id, cash)
        _make_holding(pg_sessionmaker, kakao_id, "005930", "삼성전자")

        monkeypatch.setattr(
            trade_service.StockService,
            "get_price",
            classmethod(
                lambda cls, q: {"code": "005930", "name": "삼성전자", "price": 100_000}
            ),
        )
        monkeypatch.setattr(trade_service, "is_trading_available", lambda: True)

        def buy_max(_index):
            db = pg_sessionmaker()
            try:
                return TradeService.buy_max(db, kakao_id, "삼성전자")
            finally:
                db.close()

        results = _run_concurrently(buy_max, 6)
        succeeded = [r for r in results if isinstance(r, dict) and r.get("success")]

        db = pg_sessionmaker()
        try:
            user = db.query(User).filter(User.kakao_id == kakao_id).one()
            final_cash = user.cash
        finally:
            db.close()

        assert succeeded, "전량 매수가 한 번도 성공하지 않았다 (테스트가 무의미)"
        assert final_cash >= 0, f"잔액이 음수가 됐다: {final_cash:,}"
        # 첫 성공이 잔고를 거의 다 쓰므로 이후 요청은 살 수량이 없다
        assert len(succeeded) == 1, (
            f"전량 매수가 {len(succeeded)}건 성공 — 초과 지출했다 "
            f"(최종 잔액 {final_cash:,})"
        )

    def test_buy_max_adapts_to_cash_reduced_during_price_lookup(
        self, pg_sessionmaker, monkeypatch
    ):
        """
        시세 조회 중 잔고가 줄어도, 전량 매수는 줄어든 잔고에 맞춰 성공해야 한다.

        검증하는 것: 사용자 관점의 결과(살 수 있으면 산다).
        검증하지 못하는 것: 수량 계산이 락 앞/뒤 어디서 일어나는지.
          _buy_stock_locked가 잔고를 다시 검증하므로, 수량이 과다 산정돼도
          초과 지출은 발생하지 않고 그냥 실패한다. 즉 이 테스트는 안전성
          가드이지 구현 위치를 고정하지는 않는다.
          (락 보유 구간 자체는 test_slow_price_lookup_does_not_hold_row_lock이
           검증한다)
        """
        from services import trade_service
        from services.trade_service import TradeService

        kakao_id = "buymax_lockread"
        _make_user(pg_sessionmaker, kakao_id, 1_000_000)
        _make_holding(pg_sessionmaker, kakao_id, "005930", "삼성전자")

        in_price_lookup = threading.Event()
        cash_reduced = threading.Event()

        def slow_price(cls, query):
            in_price_lookup.set()
            cash_reduced.wait(timeout=5)
            return {"code": "005930", "name": "삼성전자", "price": 100_000}

        monkeypatch.setattr(
            trade_service.StockService, "get_price", classmethod(slow_price)
        )
        monkeypatch.setattr(trade_service, "is_trading_available", lambda: True)

        result = {}

        def run_buy_max():
            db = pg_sessionmaker()
            try:
                result["value"] = TradeService.buy_max(db, kakao_id, "삼성전자")
            finally:
                db.close()

        worker = threading.Thread(target=run_buy_max)
        worker.start()
        assert in_price_lookup.wait(timeout=5)

        # 시세 조회 중 잔고를 100만 → 50만으로 줄인다 (5주는 살 수 있음)
        db = pg_sessionmaker()
        try:
            db.execute(
                text("UPDATE users SET cash = 500000 WHERE kakao_id = :kid").bindparams(
                    kid=kakao_id
                )
            )
            db.commit()
        finally:
            db.close()
        cash_reduced.set()
        worker.join(timeout=10)

        outcome = result["value"]
        assert outcome.get("success") is True, (
            f"줄어든 잔고로도 매수 가능한데 실패했다: {outcome.get('message')}"
        )
        # 50만원으로 살 수 있는 수량 (수수료 포함) 이하여야 한다
        assert outcome["data"]["quantity"] <= 5, (
            f"수량 {outcome['data']['quantity']}주 — 줄기 전 잔고로 계산했다"
        )
