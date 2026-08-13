"""
KIS 토큰 영속화 / 발급 타임아웃 테스트

배경:
  토큰은 24시간 유효한데 프로세스 메모리(클래스 변수)에만 있었다.
  재배포·콜드스타트마다 프로세스가 새로 뜨면 토큰도 같이 사라져 매번
  재발급을 시도하는데, KIS는 토큰 '발급' 자체에 유량 제한을 걸어둔다.
  게다가 발급은 시세 조회보다 느린데도 조회용 타임아웃(1.5초)을 그대로 써서
  기동 시점에 타임아웃으로 실패하곤 했다. 발급이 실패하면 그 뒤 모든
  시세 조회가 통째로 막힌다.

검증:
  - 재기동(메모리 소실) 후에도 DB에 남은 유효 토큰을 재사용한다
  - 만료된 저장 토큰은 재사용하지 않는다
  - 발급에 성공하면 DB에 저장한다
  - DB가 죽어도 발급 자체는 동작한다
  - 발급에는 조회용이 아닌 토큰 전용 타임아웃을 쓴다
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import ApiToken, Base
from services import stock_service
from services.stock_service import KISAPIClient
from settings import KISConfig


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        return self._payload


def _naive_utc(dt: datetime) -> datetime:
    """모델 규약대로 naive UTC로 변환"""
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


@pytest.fixture
def token_db():
    """
    stock_service가 쓰는 SessionLocal을 테스트 DB로 바꿔치기한다.

    StaticPool 대신 파일 없는 공유 인메모리 엔진을 쓰기 위해 단일 엔진에서
    세션을 만들어 준다(같은 커넥션을 재사용해야 테이블이 유지된다).
    """
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    with patch.object(stock_service, "SessionLocal", TestSession):
        yield TestSession

    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def clean_token_state():
    """토큰 클래스 변수와 서킷 상태를 테스트마다 초기화"""
    prev_token = KISAPIClient._access_token
    prev_expiry = KISAPIClient._token_expires_at
    KISAPIClient._access_token = None
    KISAPIClient._token_expires_at = None
    stock_service._circuit_breaker.reset()
    with (
        patch.object(stock_service.KISConfig, "APP_KEY", "key"),
        patch.object(stock_service.KISConfig, "APP_SECRET", "secret"),
    ):
        yield
    stock_service._circuit_breaker.reset()
    KISAPIClient._access_token = prev_token
    KISAPIClient._token_expires_at = prev_expiry


class TestTokenTtl:
    def test_uses_expires_in_minus_margin(self):
        """KIS가 준 expires_in에서 안전 여유를 뺀 값을 쓴다"""
        ttl = KISAPIClient._token_ttl(86400)
        assert ttl == timedelta(seconds=86400) - KISAPIClient.TOKEN_EXPIRY_MARGIN

    def test_falls_back_when_expires_in_missing(self):
        """expires_in이 없으면 기본 유효기간을 가정한다"""
        assert (
            KISAPIClient._token_ttl(None)
            == KISAPIClient.TOKEN_DEFAULT_LIFETIME - KISAPIClient.TOKEN_EXPIRY_MARGIN
        )

    def test_never_returns_non_positive(self):
        """expires_in이 여유보다 짧아도 음수/0이 되지 않는다"""
        assert KISAPIClient._token_ttl(10) >= timedelta(minutes=1)


class TestTokenSurvivesRestart:
    def test_valid_stored_token_is_reused_without_http(self, token_db):
        """재기동 후에도 DB에 남은 유효 토큰을 쓰고 재발급하지 않는다"""
        session = token_db()
        session.add(
            ApiToken(
                provider=KISAPIClient.TOKEN_PROVIDER,
                access_token="stored-token",
                expires_at=_naive_utc(datetime.now(timezone.utc) + timedelta(hours=5)),
            )
        )
        session.commit()
        session.close()

        # 프로세스 재기동 = 메모리 토큰 없음 (clean_token_state가 이미 비워둠)
        with patch.object(stock_service.requests, "post") as mock_post:
            token = KISAPIClient.get_access_token()

        assert token == "stored-token"
        assert mock_post.call_count == 0, "저장된 토큰이 있는데 재발급을 시도했다"

    def test_expired_stored_token_triggers_reissue(self, token_db):
        """만료된 저장 토큰은 재사용하지 않는다"""
        session = token_db()
        session.add(
            ApiToken(
                provider=KISAPIClient.TOKEN_PROVIDER,
                access_token="expired-token",
                expires_at=_naive_utc(
                    datetime.now(timezone.utc) - timedelta(minutes=1)
                ),
            )
        )
        session.commit()
        session.close()

        with patch.object(
            stock_service.requests,
            "post",
            return_value=FakeResponse(
                200, {"access_token": "fresh-token", "expires_in": 86400}
            ),
        ) as mock_post:
            token = KISAPIClient.get_access_token()

        assert token == "fresh-token"
        assert mock_post.call_count == 1

    def test_issued_token_is_persisted(self, token_db):
        """발급에 성공하면 다음 재기동을 위해 DB에 저장한다"""
        with patch.object(
            stock_service.requests,
            "post",
            return_value=FakeResponse(
                200, {"access_token": "new-token", "expires_in": 86400}
            ),
        ):
            assert KISAPIClient.get_access_token() == "new-token"

        session = token_db()
        row = (
            session.query(ApiToken)
            .filter(ApiToken.provider == KISAPIClient.TOKEN_PROVIDER)
            .first()
        )
        assert row is not None, "발급받은 토큰이 저장되지 않았다"
        assert row.access_token == "new-token"
        assert row.expires_at > datetime.now(timezone.utc).replace(tzinfo=None)
        session.close()

    def test_persisted_token_overwrites_previous_row(self, token_db):
        """재발급 시 기존 행을 덮어쓴다 (PK 충돌로 실패하면 안 된다)"""
        session = token_db()
        session.add(
            ApiToken(
                provider=KISAPIClient.TOKEN_PROVIDER,
                access_token="old-token",
                expires_at=_naive_utc(datetime.now(timezone.utc) - timedelta(hours=1)),
            )
        )
        session.commit()
        session.close()

        with patch.object(
            stock_service.requests,
            "post",
            return_value=FakeResponse(
                200, {"access_token": "rotated-token", "expires_in": 86400}
            ),
        ):
            assert KISAPIClient.get_access_token() == "rotated-token"

        session = token_db()
        rows = (
            session.query(ApiToken)
            .filter(ApiToken.provider == KISAPIClient.TOKEN_PROVIDER)
            .all()
        )
        assert len(rows) == 1
        assert rows[0].access_token == "rotated-token"
        session.close()

    def test_db_failure_does_not_break_issuance(self):
        """DB가 죽어도 토큰 발급 자체는 성공해야 한다"""
        from sqlalchemy.exc import OperationalError

        def broken_session():
            raise OperationalError("SELECT 1", {}, Exception("DB 연결 실패"))

        with (
            patch.object(stock_service, "SessionLocal", broken_session),
            patch.object(
                stock_service.requests,
                "post",
                return_value=FakeResponse(
                    200, {"access_token": "resilient-token", "expires_in": 86400}
                ),
            ),
        ):
            assert KISAPIClient.get_access_token() == "resilient-token"

    def test_missing_access_token_field_is_rejected(self, token_db):
        """200이어도 access_token이 없으면 토큰으로 취급하지 않는다"""
        with patch.object(
            stock_service.requests,
            "post",
            return_value=FakeResponse(200, {"msg1": "권한 없음"}),
        ):
            assert KISAPIClient.get_access_token() is None

        session = token_db()
        assert session.query(ApiToken).count() == 0, "빈 토큰을 저장했다"
        session.close()


class TestTokenTimeout:
    def test_issuance_uses_token_timeout_not_price_timeout(self, token_db):
        """
        발급은 조회보다 느리고 실패 시 전체 조회가 막히므로
        조회용(API_TIMEOUT)이 아닌 토큰 전용 타임아웃을 써야 한다.
        """
        captured = {}

        def capture_post(url, headers=None, json=None, timeout=None):
            captured["timeout"] = timeout
            return FakeResponse(200, {"access_token": "t", "expires_in": 86400})

        with patch.object(stock_service.requests, "post", side_effect=capture_post):
            KISAPIClient.get_access_token()

        assert captured["timeout"] == KISConfig.TOKEN_TIMEOUT, (
            f"발급 타임아웃이 {captured['timeout']}초 — "
            f"토큰 전용({KISConfig.TOKEN_TIMEOUT}초)이 적용되지 않았다"
        )

    def test_token_timeout_is_longer_than_price_timeout(self):
        """설정 자체가 조회용보다 넉넉해야 의미가 있다"""
        assert KISConfig.TOKEN_TIMEOUT > KISConfig.API_TIMEOUT

    def test_request_budget_still_caps_token_timeout(self, token_db):
        """
        요청 처리 중에는 카카오 SLA가 있으므로 남은 예산으로 다시 잘려야 한다.
        (기동 시점에만 TOKEN_TIMEOUT 전체를 쓴다)
        """
        from utils import budget

        captured = {}

        def capture_post(url, headers=None, json=None, timeout=None):
            captured["timeout"] = timeout
            return FakeResponse(200, {"access_token": "t", "expires_in": 86400})

        with patch.object(stock_service.requests, "post", side_effect=capture_post):
            with budget.request_budget(1.0):
                KISAPIClient.get_access_token()

        assert captured["timeout"] <= 1.0, (
            f"남은 예산(1.0초)을 넘는 타임아웃 {captured['timeout']}초를 썼다"
        )
