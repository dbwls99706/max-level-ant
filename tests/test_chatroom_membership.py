"""
그룹 채팅방 멤버 등록 타이밍 테스트

배경:
  chatroom_members는 users를 FK로 참조하므로 유저 행이 있어야 등록된다.
  그런데 등록은 명령 처리 '앞'에서만 이뤄졌다. 그룹방에서의 첫 `/시작`은
  바로 그 명령이 유저를 만들기 때문에, 등록 시점에는 아직 유저가 없어
  통째로 건너뛰어졌다. 결과적으로 새 유저는 다음 명령을 칠 때까지
  그 방의 랭킹·멤버 목록에서 빠져 있었다.

검증:
  - 그룹방 첫 `/시작` 한 번으로 멤버십이 생긴다
  - 기존 유저의 일반 명령 동작은 그대로다 (중복 등록/추가 쿼리 없음)
  - 1:1(그룹키 없음)에서는 아무것도 등록하지 않는다
  - 중복 등록(동시 요청)이 unique 제약에 걸려도 실패로 취급하지 않는다
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
from game_config import GameConfig
from handlers.command_handler import CommandHandler
from models import Base, ChatRoomMember, User
from services.user_service import register_chatroom_member

GROUP_KEY = "group-abc-123"


@pytest.fixture
def shared_db(monkeypatch):
    """
    register_chatroom_member는 메인 세션 오염을 피하려고 database.SessionLocal로
    별도 세션을 연다. 같은 인메모리 DB를 보게 하려면 StaticPool로 커넥션을
    공유해야 한다 (기본 인메모리 SQLite는 커넥션마다 DB가 따로 생긴다).
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    monkeypatch.setattr(database, "SessionLocal", TestSession)

    session = TestSession()
    yield session
    session.close()


def _members(session, group_key=GROUP_KEY):
    return (
        session.query(ChatRoomMember)
        .filter(ChatRoomMember.group_key == group_key)
        .all()
    )


def _make_user(session, kakao_id):
    session.add(
        User(
            kakao_id=kakao_id,
            nickname="기존유저",
            cash=GameConfig.INITIAL_CASH,
            initial_cash=GameConfig.INITIAL_CASH,
            attendance_streak=0,
            ad_count_today=0,
        )
    )
    session.commit()


class TestFirstStartInGroup:
    def test_membership_created_on_first_start(self, shared_db):
        """그룹방 첫 `/시작` 한 번으로 멤버십이 생겨야 한다"""
        CommandHandler(
            shared_db, "newbie_1", "/시작", nickname="새싹", group_key=GROUP_KEY
        ).handle()

        members = _members(shared_db)
        assert len(members) == 1, (
            "첫 /시작 후에도 멤버십이 없다 — 다음 명령까지 방 랭킹에서 빠진다"
        )
        assert members[0].kakao_id == "newbie_1"

    def test_user_row_is_actually_created(self, shared_db):
        """전제 확인: /시작이 유저를 만든다"""
        CommandHandler(
            shared_db, "newbie_2", "/시작", nickname="새싹", group_key=GROUP_KEY
        ).handle()
        assert shared_db.query(User).filter(User.kakao_id == "newbie_2").first()

    def test_second_command_does_not_duplicate(self, shared_db):
        """첫 턴에 등록됐으니 두 번째 명령이 행을 늘리면 안 된다"""
        CommandHandler(
            shared_db, "newbie_3", "/시작", nickname="새싹", group_key=GROUP_KEY
        ).handle()
        CommandHandler(shared_db, "newbie_3", "/도움말", group_key=GROUP_KEY).handle()

        assert len(_members(shared_db)) == 1


class TestExistingBehaviorUnchanged:
    def test_existing_user_registered_before_command(self, shared_db):
        """이미 유저가 있으면 종전처럼 명령 처리 전에 등록된다"""
        _make_user(shared_db, "veteran_1")
        CommandHandler(shared_db, "veteran_1", "/도움말", group_key=GROUP_KEY).handle()

        assert len(_members(shared_db)) == 1

    def test_existing_user_does_not_register_twice(self, shared_db, monkeypatch):
        """
        앞에서 등록에 성공했으면 뒤에서 다시 부르지 않아야 한다.
        (매 요청마다 DB 왕복이 두 번씩 늘어나면 5초 SLA에 손해다)
        """
        _make_user(shared_db, "veteran_2")

        calls = []
        import handlers.command_handler as ch

        real = ch.register_chatroom_member

        def counting(db, group_key, kakao_id):
            calls.append(kakao_id)
            return real(db, group_key, kakao_id)

        monkeypatch.setattr(ch, "register_chatroom_member", counting)
        CommandHandler(shared_db, "veteran_2", "/도움말", group_key=GROUP_KEY).handle()

        assert len(calls) == 1, f"등록을 {len(calls)}번 시도했다 (1번이면 충분)"

    def test_direct_chat_registers_nothing(self, shared_db):
        """1:1 대화(group_key 없음)에서는 멤버십을 만들지 않는다"""
        CommandHandler(shared_db, "solo_1", "/시작", nickname="혼자").handle()

        assert shared_db.query(ChatRoomMember).count() == 0

    def test_response_is_returned_unchanged(self, shared_db):
        """등록 로직이 응답을 가로채면 안 된다"""
        resp = CommandHandler(
            shared_db, "newbie_4", "/시작", nickname="새싹", group_key=GROUP_KEY
        ).handle()

        assert resp.get("version") == "2.0"
        assert resp["template"]["outputs"], "응답 말풍선이 비었다"


class TestRegisterHelper:
    def test_returns_false_when_user_missing(self, shared_db):
        """유저가 없으면 등록하지 못했음을 알려야 한다"""
        assert register_chatroom_member(shared_db, GROUP_KEY, "ghost") is False
        assert shared_db.query(ChatRoomMember).count() == 0

    def test_returns_true_when_registered(self, shared_db):
        _make_user(shared_db, "member_1")
        assert register_chatroom_member(shared_db, GROUP_KEY, "member_1") is True

    def test_repeat_call_updates_instead_of_duplicating(self, shared_db):
        """이미 있는 멤버는 last_active만 갱신한다"""
        _make_user(shared_db, "member_2")
        assert register_chatroom_member(shared_db, GROUP_KEY, "member_2") is True
        assert register_chatroom_member(shared_db, GROUP_KEY, "member_2") is True

        assert len(_members(shared_db)) == 1

    def test_unique_violation_is_treated_as_success(self, shared_db, monkeypatch):
        """
        동시 요청으로 다른 쪽이 먼저 INSERT하면 unique(group_key, kakao_id)에
        걸려 IntegrityError가 난다. 멤버십은 이미 존재하므로 실패로 보고하면
        안 된다 — False를 돌려주면 호출부가 없는 문제를 고치려 든다.
        """
        _make_user(shared_db, "member_3")

        import sqlalchemy.orm as orm
        from sqlalchemy.exc import IntegrityError

        real_commit = orm.Session.commit

        def commit_conflict(self):
            raise IntegrityError(
                "INSERT INTO chatroom_members", {}, Exception("unique_chatroom_member")
            )

        monkeypatch.setattr(orm.Session, "commit", commit_conflict)
        try:
            assert register_chatroom_member(shared_db, GROUP_KEY, "member_3") is True
        finally:
            monkeypatch.setattr(orm.Session, "commit", real_commit)

    def test_other_db_errors_are_reported_as_failure(self, shared_db, monkeypatch):
        """unique 충돌이 아닌 진짜 실패는 True로 감추면 안 된다"""
        _make_user(shared_db, "member_4")

        import sqlalchemy.orm as orm
        from sqlalchemy.exc import OperationalError

        real_commit = orm.Session.commit

        def commit_broken(self):
            raise OperationalError("INSERT", {}, Exception("디스크 오류"))

        monkeypatch.setattr(orm.Session, "commit", commit_broken)
        try:
            assert register_chatroom_member(shared_db, GROUP_KEY, "member_4") is False
        finally:
            monkeypatch.setattr(orm.Session, "commit", real_commit)
