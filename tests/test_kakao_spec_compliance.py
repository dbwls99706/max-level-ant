"""
카카오 스킬 응답 스펙 준수 테스트

응답 JSON이 카카오 명세 한도를 넘으면 카카오가 응답을 거부할 수 있다.
컴포넌트 한도를 한곳에서 검증하고, 실제 핸들러 응답에도 적용한다.

명세: https://kakaobusiness.gitbook.io/main/tool/chatbot/skill_guide/answer_json_format
- template.outputs: 1~3개
- simpleText: text 최대 1000자
- simpleImage: altText 최대 50자
- textCard: title 50자, title+description 합산 400자, title/description 중 하나 필수
- basicCard: title 50자, description 230자, thumbnail 필수
- listCard: header 필수, items 최대 5개
- 버튼: 세로 3 / 가로 2

한계: 핸들러 검증 대상은 외부 API가 필요 없는 OFFLINE_COMMANDS 뿐이다.
/시세·/검색·/급등 같은 KIS 의존 경로는 여기서 다루지 않는다.
"""

import pytest

from utils import KakaoResponse

# 카카오 명세 한도 (KakaoResponse 상수와 별개로 여기에 다시 적어 둔다.
# 구현 상수를 그대로 참조하면 상수를 잘못 바꿔도 테스트가 같이 통과해버린다.)
SPEC_MAX_OUTPUTS = 3
SPEC_SIMPLE_TEXT_CHARS = 1000
SPEC_ALT_TEXT_CHARS = 50
SPEC_CARD_TITLE_CHARS = 50
SPEC_TEXT_CARD_CHARS = 400
SPEC_BASIC_CARD_CHARS = 230
SPEC_LIST_ITEMS = 5
SPEC_BUTTONS_VERTICAL = 3
SPEC_BUTTONS_HORIZONTAL = 2


def assert_valid_skill_response(resp: dict, label: str = ""):
    """카카오 스킬 응답이 명세 한도를 지키는지 검증"""
    where = f"[{label}] " if label else ""

    assert resp.get("version") == "2.0", f"{where}version은 '2.0'이어야 한다"
    outputs = resp["template"]["outputs"]
    assert 1 <= len(outputs) <= SPEC_MAX_OUTPUTS, (
        f"{where}outputs는 1~{SPEC_MAX_OUTPUTS}개여야 하는데 {len(outputs)}개"
    )

    for out in outputs:
        assert len(out) == 1, f"{where}output 하나에 컴포넌트는 하나여야 한다"
        kind, body = next(iter(out.items()))

        if kind == "simpleText":
            chars = len(body.get("text", ""))
            assert 0 < chars <= SPEC_SIMPLE_TEXT_CHARS, (
                f"{where}simpleText {chars}자 > {SPEC_SIMPLE_TEXT_CHARS}자"
            )
        elif kind == "simpleImage":
            assert body.get("imageUrl"), f"{where}simpleImage imageUrl 필수"
            alt = len(body.get("altText", ""))
            assert alt <= SPEC_ALT_TEXT_CHARS, (
                f"{where}simpleImage altText {alt}자 > {SPEC_ALT_TEXT_CHARS}자"
            )
        elif kind == "textCard":
            title = body.get("title", "")
            desc = body.get("description", "")
            assert title or desc, f"{where}textCard는 title/description 중 하나가 필수"
            assert len(title) <= SPEC_CARD_TITLE_CHARS, (
                f"{where}textCard title {len(title)}자 > {SPEC_CARD_TITLE_CHARS}자"
            )
            chars = len(title) + len(desc)
            assert chars <= SPEC_TEXT_CARD_CHARS, (
                f"{where}textCard title+description {chars}자 "
                f"> {SPEC_TEXT_CARD_CHARS}자"
            )
        elif kind == "basicCard":
            title = body.get("title", "")
            assert len(title) <= SPEC_CARD_TITLE_CHARS, (
                f"{where}basicCard title {len(title)}자 > {SPEC_CARD_TITLE_CHARS}자"
            )
            chars = len(body.get("description", ""))
            assert chars <= SPEC_BASIC_CARD_CHARS, (
                f"{where}basicCard description {chars}자 > {SPEC_BASIC_CARD_CHARS}자"
            )
            assert (body.get("thumbnail") or {}).get("imageUrl"), (
                f"{where}basicCard는 thumbnail이 필수"
            )
        elif kind == "listCard":
            assert (body.get("header") or {}).get("title"), (
                f"{where}listCard는 header.title이 필수"
            )
            items = body.get("items", [])
            assert items, f"{where}listCard items가 비어 있다"
            assert len(items) <= SPEC_LIST_ITEMS, (
                f"{where}listCard items {len(items)}개 > {SPEC_LIST_ITEMS}개"
            )
            for item in items:
                assert item.get("title"), f"{where}listCard item title 필수"
        else:
            raise AssertionError(f"{where}알 수 없는 컴포넌트: {kind}")

        buttons = body.get("buttons") or []
        layout = body.get("buttonLayout", "vertical")
        cap = SPEC_BUTTONS_VERTICAL if layout == "vertical" else SPEC_BUTTONS_HORIZONTAL
        assert len(buttons) <= cap, (
            f"{where}{kind} 버튼 {len(buttons)}개 > {layout} 한도 {cap}개"
        )
        for btn in buttons:
            assert "label" in btn and "action" in btn, f"{where}버튼 필드 누락: {btn}"


class TestComponentLimits:
    """헬퍼가 스펙 한도를 강제하는지"""

    def test_text_with_buttons_caps_buttons(self):
        btns = [
            {"label": f"B{i}", "action": "message", "messageText": f"/{i}"}
            for i in range(10)
        ]
        resp = KakaoResponse.text_with_buttons("본문", btns)
        assert_valid_skill_response(resp, "text_with_buttons")

    def test_text_card_title_counts_toward_limit(self):
        """textCard는 title+description 합산 400자이므로 title도 예산을 쓴다"""
        title = "제" * 200
        resp = KakaoResponse.text_card(title, "설" * 500)
        assert_valid_skill_response(resp, "text_card")

    def test_basic_card_description_capped(self):
        resp = KakaoResponse.basic_card("제목", "설" * 1000, "https://img/x.png")
        assert_valid_skill_response(resp, "basic_card")
        desc = resp["template"]["outputs"][0]["basicCard"]["description"]
        assert len(desc) <= SPEC_BASIC_CARD_CHARS

    def test_basic_card_requires_thumbnail(self):
        """basicCard의 thumbnail은 명세상 필수"""
        with pytest.raises(ValueError):
            KakaoResponse.basic_card("제목", "설명", "")

    def test_card_titles_capped_at_50(self):
        resp = KakaoResponse.text_card("제" * 300, "설명")
        assert_valid_skill_response(resp, "text_card title")
        resp = KakaoResponse.basic_card("제" * 300, "설명", "https://img/x.png")
        assert_valid_skill_response(resp, "basic_card title")

    def test_text_card_requires_title_or_description(self):
        with pytest.raises(ValueError):
            KakaoResponse.text_card("", "")

    def test_simple_text_capped_at_1000(self):
        resp = KakaoResponse.simple_text("가" * 5000)
        assert_valid_skill_response(resp, "simple_text")
        assert (
            len(resp["template"]["outputs"][0]["simpleText"]["text"])
            <= SPEC_SIMPLE_TEXT_CHARS
        )

    def test_simple_image_alt_text_capped(self):
        resp = KakaoResponse.simple_image("https://img/x.png", "설" * 300)
        assert_valid_skill_response(resp, "simple_image")

    def test_list_card_items_capped(self):
        items = [{"title": f"항목{i}", "description": "설명"} for i in range(20)]
        resp = KakaoResponse.list_card("헤더", items)
        assert_valid_skill_response(resp, "list_card")

    def test_list_card_keeps_group_ranking_layout(self):
        """그룹 챗봇 전용 '리스트(랭킹)' 말풍선 지정이 유지된다"""
        items = [{"title": f"{i}위", "description": "+1.0%"} for i in range(3)]
        resp = KakaoResponse.list_card("랭킹", items, list_layout="ranking")
        card = resp["template"]["outputs"][0]["listCard"]
        assert card["listLayout"] == "ranking"
        assert_valid_skill_response(resp, "list_card(ranking)")

    def test_body_limit_is_below_spec_limit(self):
        """본문 UX 한도는 스펙 상한보다 보수적이어야 한다 (그룹방 화면 가림 방지)"""
        assert KakaoResponse.BODY_LIMIT <= KakaoResponse.TEXT_CARD_LIMIT
        assert KakaoResponse.MAX_VERTICAL_BUTTONS == SPEC_BUTTONS_VERTICAL
        assert KakaoResponse.MAX_HORIZONTAL_BUTTONS == SPEC_BUTTONS_HORIZONTAL


# 실제 핸들러가 만드는 응답을 명세로 검증한다.
# 외부 API가 필요 없는(순수 응답 조립) 명령어만 대상으로 한다.
OFFLINE_COMMANDS = [
    "/시작",
    "/도움말",
    "/도움말주식",
    "/도움말자산",
    "/도움말게임",
    "/도움말소셜",
    "/잔고",
    "/출석",
    "/보물상자",
    "/미션",
    "/업적",
    "/챌린지",
    "/마일스톤",
    "/랭킹",
    "/각성랭킹",
    "/내순위",
    "/배틀목록",
    "/거래내역",
    "/능력",
    "/알수없는명령어",
    "",
]


class TestHandlerResponses:
    """핸들러가 실제로 만드는 응답이 스펙을 지키는지"""

    @pytest.mark.parametrize("command", OFFLINE_COMMANDS)
    def test_command_response_is_spec_compliant(self, db, test_user, command):
        from handlers import CommandHandler

        handler = CommandHandler(db, test_user.kakao_id, command, "테스터", "")
        resp = handler.handle()
        assert_valid_skill_response(resp, command or "(빈 발화)")

    @pytest.mark.parametrize("command", OFFLINE_COMMANDS)
    def test_group_chat_response_is_spec_compliant(self, db, test_user, command):
        """그룹 채팅방(botGroupKey 있음) 경로도 동일하게 검증"""
        from handlers import CommandHandler

        handler = CommandHandler(
            db, test_user.kakao_id, command, "테스터", "group-key-1"
        )
        resp = handler.handle()
        assert_valid_skill_response(resp, f"group:{command or '(빈 발화)'}")
