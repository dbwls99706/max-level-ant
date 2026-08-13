"""
/skill 엔드포인트 인증 테스트

/skill은 공개 POST 엔드포인트다. 공유 비밀키 검증이 없으면 누구나
임의의 userRequest.user.id로 게임 명령을 실행할 수 있고, ID를 바꿔가며
유저별 rate limit도 우회할 수 있다.
"""

import pytest
from fastapi.testclient import TestClient

import main
from security import SecurityConfig

SKILL_PAYLOAD = {"userRequest": {"user": {"id": "authtester"}, "utterance": "/도움말"}}


TEST_KEY = "s3cret-skill-key"


@pytest.fixture
def client(monkeypatch):
    """
    핸들러를 가볍게 대체해 인증 동작만 검증한다.

    기동 가드(키 없으면 RuntimeError)에 걸리지 않도록 TestClient를 띄우기
    전에 키를 설정해 둔다. 개별 테스트는 그 뒤에 설정을 바꿔도 되는데,
    키 검사는 요청마다 이뤄지기 때문이다.
    """
    monkeypatch.setattr(SecurityConfig, "SKILL_API_KEY", TEST_KEY)
    monkeypatch.setattr(SecurityConfig, "SKILL_API_KEY_HEADER", "X-Skill-Key")
    monkeypatch.setattr(SecurityConfig, "DEV_MODE", False)
    monkeypatch.setattr(
        main.CommandHandler,
        "handle",
        lambda self: main.KakaoResponse.simple_text("ok"),
    )
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def with_key():
    """client 픽스처가 설정해 둔 스킬 키"""
    return TEST_KEY


class TestSkillKeyRequired:
    def test_correct_key_is_accepted(self, client, with_key):
        resp = client.post(
            "/skill", json=SKILL_PAYLOAD, headers={"X-Skill-Key": with_key}
        )
        assert resp.status_code == 200

    def test_missing_key_is_rejected(self, client, with_key):
        resp = client.post("/skill", json=SKILL_PAYLOAD)
        assert resp.status_code == 403

    def test_wrong_key_is_rejected(self, client, with_key):
        resp = client.post(
            "/skill", json=SKILL_PAYLOAD, headers={"X-Skill-Key": "wrong-key"}
        )
        assert resp.status_code == 403

    def test_empty_key_header_is_rejected(self, client, with_key):
        resp = client.post("/skill", json=SKILL_PAYLOAD, headers={"X-Skill-Key": ""})
        assert resp.status_code == 403

    def test_rejected_before_any_game_command_runs(self, client, with_key, monkeypatch):
        """
        인증 실패 요청은 핸들러까지 도달하면 안 된다.
        (도달하면 /시작이 DB에 유저를 만들어버린다)
        """
        called = []
        monkeypatch.setattr(
            main.CommandHandler,
            "handle",
            lambda self: called.append(1) or main.KakaoResponse.simple_text("ok"),
        )
        resp = client.post(
            "/skill",
            json={"userRequest": {"user": {"id": "attacker"}, "utterance": "/시작"}},
        )
        assert resp.status_code == 403
        assert not called, "인증 실패했는데 명령이 실행됐다"

    def test_custom_header_name_is_honored(self, client, monkeypatch):
        monkeypatch.setattr(SecurityConfig, "SKILL_API_KEY", "abc123")
        monkeypatch.setattr(SecurityConfig, "SKILL_API_KEY_HEADER", "X-Custom-Auth")
        monkeypatch.setattr(SecurityConfig, "DEV_MODE", False)

        assert (
            client.post(
                "/skill", json=SKILL_PAYLOAD, headers={"X-Skill-Key": "abc123"}
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/skill", json=SKILL_PAYLOAD, headers={"X-Custom-Auth": "abc123"}
            ).status_code
            == 200
        )


class TestDevModeFallback:
    def test_dev_mode_without_key_allows_request(self, client, monkeypatch):
        """로컬 개발 편의: 키가 없고 DEV_MODE면 통과시킨다"""
        monkeypatch.setattr(SecurityConfig, "SKILL_API_KEY", "")
        monkeypatch.setattr(SecurityConfig, "DEV_MODE", True)
        resp = client.post("/skill", json=SKILL_PAYLOAD)
        assert resp.status_code == 200

    def test_production_without_key_rejects_request(self, client, monkeypatch):
        """운영 환경에서 키가 없으면(기동 검사를 우회했더라도) 통과시키지 않는다"""
        monkeypatch.setattr(SecurityConfig, "SKILL_API_KEY", "")
        monkeypatch.setattr(SecurityConfig, "DEV_MODE", False)
        resp = client.post("/skill", json=SKILL_PAYLOAD)
        assert resp.status_code == 403


class TestVerifyHelper:
    def test_uses_constant_time_comparison(self):
        """타이밍 공격 방지를 위해 secrets.compare_digest를 쓴다"""
        import inspect

        source = inspect.getsource(SecurityConfig.verify_skill_key)
        assert "compare_digest" in source

    def test_key_configured_flag(self, monkeypatch):
        monkeypatch.setattr(SecurityConfig, "SKILL_API_KEY", "")
        assert SecurityConfig.is_skill_key_configured() is False
        monkeypatch.setattr(SecurityConfig, "SKILL_API_KEY", "x")
        assert SecurityConfig.is_skill_key_configured() is True


class TestStartupGuard:
    def test_production_startup_fails_without_key(self, monkeypatch):
        """운영 환경에서 키가 없으면 서버가 아예 뜨지 않아야 한다"""
        monkeypatch.setattr(SecurityConfig, "SKILL_API_KEY", "")
        monkeypatch.setattr(SecurityConfig, "DEV_MODE", False)

        with pytest.raises(RuntimeError, match="SKILL_API_KEY"):
            with TestClient(main.app):
                pass

    def test_production_startup_succeeds_with_key(self, monkeypatch):
        monkeypatch.setattr(SecurityConfig, "SKILL_API_KEY", "configured")
        monkeypatch.setattr(SecurityConfig, "DEV_MODE", False)

        with TestClient(main.app) as c:
            assert c.get("/").status_code == 200
