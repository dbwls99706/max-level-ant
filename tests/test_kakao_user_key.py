"""
카카오 botUserKey(userRequest.user.id) 취급 테스트

배경:
  예전에는 /skill이 유저 ID를 [A-Za-z0-9_-]+ 정규식으로 걸렀다. 이는 카카오
  문서가 보장하지 않는 제약이다. botUserKey는 내용에 의미를 부여하지 않는
  opaque identifier이므로, 카카오가 표현을 바꾸거나 다른 문자를 쓰기 시작하면
  멀쩡한 유저가 통째로 로그인 불가가 된다.

  따라서 '무엇으로 이루어졌는지'가 아니라 '저장·조회에 쓸 수 있는지'만 본다:
  타입(str) / 빈 값 / 최대 길이 70자 / NUL 포함 여부.

검증:
  - 기존 ASCII ID는 그대로 동작한다 (회귀 방지)
  - 정규식 때문에 거부되던 유효한 opaque 문자열이 이제 처리된다
  - 핸들러에는 원본 문자열이 손상 없이 전달된다
  - 빈 값·과길이·비문자열·NUL은 여전히 거부한다
"""

import pytest
from fastapi.testclient import TestClient

import main
from security import SecurityConfig

TEST_KEY = "user-key-test"
HEADERS = {"X-Skill-Key": TEST_KEY}


@pytest.fixture
def client(monkeypatch):
    """핸들러를 대체해 ID 검증 동작만 본다. 전달된 kakao_id를 기록한다."""
    monkeypatch.setattr(SecurityConfig, "SKILL_API_KEY", TEST_KEY)
    monkeypatch.setattr(SecurityConfig, "SKILL_API_KEY_HEADER", "X-Skill-Key")
    monkeypatch.setattr(SecurityConfig, "DEV_MODE", False)

    seen = []

    def fake_init(self, db, kakao_id, utterance, nickname="", group_key=""):
        seen.append(kakao_id)
        self.kakao_id = kakao_id

    monkeypatch.setattr(main.CommandHandler, "__init__", fake_init)
    monkeypatch.setattr(
        main.CommandHandler,
        "handle",
        lambda self: main.KakaoResponse.simple_text("ok"),
    )

    with TestClient(main.app) as c:
        c.seen_ids = seen
        yield c


def _post(client, user_id, utterance="/도움말"):
    """요청을 보내고 (응답, 핸들러 도달 여부)를 돌려준다.

    거부된 요청도 200 + 안내 문구로 끝나므로, 상태 코드가 아니라
    '핸들러가 실제로 호출됐는지'로 수용 여부를 판별한다.
    """
    before = len(client.seen_ids)
    resp = client.post(
        "/skill",
        json={"userRequest": {"user": {"id": user_id}, "utterance": utterance}},
        headers=HEADERS,
    )
    return resp, len(client.seen_ids) > before


def _text_of(resp) -> str:
    """카카오 응답에서 첫 말풍선 텍스트를 뽑아낸다"""
    outputs = resp.json().get("template", {}).get("outputs", [])
    if not outputs:
        return ""
    return outputs[0].get("simpleText", {}).get("text", "")


# 검증 실패 시 안내 문구와, 예외를 삼켰을 때의 문구.
# 둘을 구분해야 '깔끔한 거부'와 '터졌는데 감춰짐'을 구별할 수 있다.
INVALID_ID_MESSAGE = "유저 정보를 확인할 수 없습니다."
CRASH_MESSAGE = "오류가 발생했습니다"


class TestExistingIdsStillWork:
    """정규식을 걷어내도 기존 ID는 그대로 동작해야 한다 (회귀 방지)"""

    @pytest.mark.parametrize(
        "user_id",
        [
            "abcdef1234567890",
            "user_with_underscore",
            "user-with-hyphen",
            "0123456789",
            "A" * 70,  # 문서상 최대 길이
        ],
    )
    def test_ascii_ids_are_accepted(self, client, user_id):
        _, accepted = _post(client, user_id)
        assert accepted, f"기존 형식 ID가 거부됐다: {user_id!r}"
        assert client.seen_ids[-1] == user_id


class TestOpaqueIdsAreAccepted:
    """예전 정규식이 거부하던, 그러나 유효한 opaque 문자열들"""

    @pytest.mark.parametrize(
        "user_id",
        [
            "user.with.dot",  # '.' — 정규식에 없던 문자
            "user@example",  # '@'
            "user+tag",  # '+'
            "abc/def",  # base64url이 아닌 표준 base64
            "abc=",  # base64 패딩
            "Zm9vYmFy==",  # 패딩 2개
            "user:123",  # ':' 구분자
            "사용자키",  # 비ASCII
            "ключ",
            "🐜ant",  # 이모지
            "{json-ish}",
        ],
    )
    def test_previously_rejected_ids_now_work(self, client, user_id):
        _, accepted = _post(client, user_id)
        assert accepted, f"opaque ID가 형식 때문에 거부됐다: {user_id!r}"

    def test_id_is_passed_through_unmodified(self, client):
        """opaque이므로 손대지 않고 그대로 넘겨야 한다 (다른 유저와 섞이면 안 됨)"""
        user_id = "  Zm9v/YmFy+ID==  "
        _post(client, user_id)
        assert client.seen_ids[-1] == user_id, "ID가 변형돼 다른 유저로 취급될 수 있다"

    def test_ids_differing_only_by_rejected_chars_stay_distinct(self, client):
        """정규식 제거로 서로 다른 ID가 하나로 합쳐지지 않아야 한다"""
        _post(client, "user.a")
        _post(client, "user.b")
        assert client.seen_ids[-2:] == ["user.a", "user.b"]


class TestInvalidIdsStillRejected:
    @pytest.mark.parametrize("user_id", ["", "   ", "\t\n"])
    def test_empty_or_blank_is_rejected(self, client, user_id):
        _, accepted = _post(client, user_id)
        assert not accepted, "빈 ID가 통과했다"

    def test_too_long_is_rejected(self, client):
        """공식 문서 기준 최대 길이(70자)를 넘으면 거부"""
        _, accepted = _post(client, "A" * 71)
        assert not accepted, "70자 초과 ID가 통과했다"

    @pytest.mark.parametrize("user_id", [12345, None, {"id": "x"}, ["a"], True])
    def test_non_string_is_rejected_cleanly(self, client, user_id):
        """
        숫자/객체가 와도 '검증 실패'로 끝나야 한다.

        타입 검사가 마스킹(len()·슬라이싱)보다 뒤에 있으면 TypeError가 나고,
        바깥 except가 그걸 삼켜 일반 오류 문구로 응답한다. 겉보기 200은
        같으므로 문구까지 확인해야 두 경우를 구분할 수 있다.
        """
        resp, accepted = _post(client, user_id)
        assert not accepted, "비문자열 ID가 통과했다"

        text = _text_of(resp)
        assert CRASH_MESSAGE not in text, (
            f"비문자열 ID에서 예외가 났다(문구: {text!r}) — 타입 검사가 늦다"
        )
        assert text == INVALID_ID_MESSAGE

    def test_nul_byte_is_rejected(self, client):
        """PostgreSQL text에 저장할 수 없어 커밋 시점에 터지므로 미리 거른다"""
        _, accepted = _post(client, "user\x00id")
        assert not accepted, "NUL이 포함된 ID가 통과했다"


class TestNoFormatRegexRemains:
    def test_max_length_matches_kakao_spec(self):
        assert main.KAKAO_USER_KEY_MAX_LENGTH == 70

    def test_format_pattern_is_gone(self):
        """형식 정규식이 남아 있으면 opaque 취급이라고 할 수 없다"""
        assert not hasattr(main, "KAKAO_ID_PATTERN"), (
            "botUserKey 형식 정규식이 아직 남아 있다"
        )
