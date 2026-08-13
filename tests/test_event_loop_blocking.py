"""
동기 DB 작업이 이벤트 루프를 막지 않는지 검증

배경:
  FastAPI에서 `async def` 엔드포인트의 본문은 이벤트 루프 스레드에서 그대로
  실행된다. 그 안에서 동기 DB 호출을 하면, DB가 느려지는 동안 그 워커 프로세스의
  '모든' 요청이 함께 멈춘다. 카카오 스킬은 5초 안에 응답해야 하므로,
  헬스체크나 관리자 작업 하나 때문에 게임 명령이 통째로 타임아웃될 수 있다.

  /skill은 이미 run_in_threadpool을 쓰지만 /health, /admin/reset-db,
  /admin/reset-seed는 루프 위에서 동기 DB 작업을 하고 있었다.

검증 방법:
  워커 스레드에는 실행 중인 이벤트 루프가 없다. 따라서 동기 함수 안에서
  asyncio.get_running_loop()이 RuntimeError를 내면 '루프 밖'이고,
  성공하면 '루프 위에서 실행 중'이라는 뜻이다. 타이밍에 의존하지 않는다.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

import main
from security import SecurityConfig

ADMIN_TOKEN = "admin-token-for-test"
AUTH = {"Authorization": f"Bearer {ADMIN_TOKEN}"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(SecurityConfig, "SKILL_API_KEY", "k")
    monkeypatch.setattr(SecurityConfig, "DEV_MODE", False)
    monkeypatch.setattr(SecurityConfig, "ADMIN_TOKEN", ADMIN_TOKEN)
    with TestClient(main.app) as c:
        yield c


def _loop_probe(record, return_value):
    """호출 시점이 이벤트 루프 위인지 기록하는 가짜 동기 작업"""

    def probe(*args, **kwargs):
        try:
            asyncio.get_running_loop()
            record.append("event_loop")
        except RuntimeError:
            record.append("worker_thread")
        return return_value

    return probe


class TestHealthCheck:
    def test_db_health_runs_off_event_loop(self, client, monkeypatch):
        """헬스체크가 느려도 스킬 요청까지 같이 멈추면 안 된다"""
        where = []
        monkeypatch.setattr(main, "check_db_health", _loop_probe(where, True))

        resp = client.get("/health")

        assert resp.status_code == 200
        assert where == ["worker_thread"], (
            "DB 헬스체크가 이벤트 루프에서 실행됐다 — DB가 느려지면 전체 요청이 멈춘다"
        )

    def test_unhealthy_db_still_reports_503(self, client, monkeypatch):
        """스레드로 옮겨도 실패 응답은 그대로여야 한다"""
        monkeypatch.setattr(main, "check_db_health", lambda: False)

        resp = client.get("/health")

        assert resp.status_code == 503
        assert resp.json()["status"] == "unhealthy"

    def test_healthy_response_shape_unchanged(self, client, monkeypatch):
        monkeypatch.setattr(main, "check_db_health", lambda: True)

        assert client.get("/health").json() == {"status": "healthy", "db": "connected"}


class TestAdminResetDb:
    def test_reset_runs_off_event_loop(self, client, monkeypatch):
        """DROP/CREATE는 오래 걸린다 — 루프에서 돌리면 서비스가 멈춘다"""
        where = []
        monkeypatch.setattr(main, "reset_db", _loop_probe(where, None))

        resp = client.post(
            "/admin/reset-db", json={"confirm": "DELETE_ALL_DATA"}, headers=AUTH
        )

        assert resp.json()["success"] is True
        assert where == ["worker_thread"], "DB 초기화가 이벤트 루프에서 실행됐다"

    def test_wrong_confirm_does_not_touch_db(self, client, monkeypatch):
        called = []
        monkeypatch.setattr(main, "reset_db", lambda: called.append(1))

        resp = client.post("/admin/reset-db", json={"confirm": "oops"}, headers=AUTH)

        assert resp.json()["success"] is False
        assert not called, "확인 문구가 틀렸는데 DB를 초기화했다"

    def test_requires_admin_token(self, client, monkeypatch):
        called = []
        monkeypatch.setattr(main, "reset_db", lambda: called.append(1))

        assert (
            client.post(
                "/admin/reset-db", json={"confirm": "DELETE_ALL_DATA"}
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/admin/reset-db",
                json={"confirm": "DELETE_ALL_DATA"},
                headers={"Authorization": "Bearer wrong"},
            ).status_code
            == 403
        )
        assert not called


class TestAdminResetSeed:
    def test_reset_runs_off_event_loop(self, client, monkeypatch):
        """전 유저 UPDATE/DELETE도 루프 밖에서 돌아야 한다"""
        where = []
        monkeypatch.setattr(
            main,
            "_reset_seed_money",
            _loop_probe(where, {"success": True, "message": "ok"}),
        )

        resp = client.post(
            "/admin/reset-seed", json={"confirm": "RESET_SEED_MONEY"}, headers=AUTH
        )

        assert resp.json()["success"] is True
        assert where == ["worker_thread"], "시드머니 초기화가 이벤트 루프에서 실행됐다"

    def test_wrong_confirm_does_not_touch_db(self, client, monkeypatch):
        called = []
        monkeypatch.setattr(
            main, "_reset_seed_money", lambda: called.append(1) or {"success": True}
        )

        resp = client.post("/admin/reset-seed", json={"confirm": "nope"}, headers=AUTH)

        assert resp.json()["success"] is False
        assert not called, "확인 문구가 틀렸는데 시드머니를 초기화했다"

    def test_requires_admin_token(self, client, monkeypatch):
        called = []
        monkeypatch.setattr(
            main, "_reset_seed_money", lambda: called.append(1) or {"success": True}
        )

        assert (
            client.post(
                "/admin/reset-seed", json={"confirm": "RESET_SEED_MONEY"}
            ).status_code
            == 401
        )
        assert not called


class TestSkillStaysOffLoop:
    def test_skill_handler_runs_off_event_loop(self, client, monkeypatch):
        """이미 적용돼 있던 동작에 대한 회귀 방지"""
        where = []

        def probing_handle(self):
            try:
                asyncio.get_running_loop()
                where.append("event_loop")
            except RuntimeError:
                where.append("worker_thread")
            return main.KakaoResponse.simple_text("ok")

        monkeypatch.setattr(main.CommandHandler, "handle", probing_handle)

        resp = client.post(
            "/skill",
            json={
                "userRequest": {"user": {"id": "loop-tester"}, "utterance": "/도움말"}
            },
            headers={"X-Skill-Key": "k"},
        )

        assert resp.status_code == 200
        assert where == ["worker_thread"]
