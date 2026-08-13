"""
카카오 스킬 응답 스펙 준수 테스트

응답 JSON이 카카오 명세 한도를 넘으면 카카오가 응답을 거부할 수 있다.
컴포넌트 한도를 한곳에서 검증하고, 실제 핸들러 응답에도 적용한다.

명세: https://kakaobusiness.gitbook.io/main/tool/chatbot/skill_guide/answer_json_format
- template.outputs: 1~3개
- textCard: title+description 합산 400자, 버튼 세로 3 / 가로 2
- basicCard: description 230자, 버튼 세로 3 / 가로 2
- listCard: items 최대 5개, 버튼 세로 3 / 가로 2
"""

import pytest

from utils import KakaoResponse

# 카카오 명세 한도 (KakaoResponse 상수와 별개로 여기에 다시 적어 둔다.
# 구현 상수를 그대로 참조하면 상수를 잘못 바꿔도 테스트가 같이 통과해버린다.)
SPEC_MAX_OUTPUTS = 3
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

        if kind == "textCard":
            chars = len(body.get("title", "")) + len(body.get("description", ""))
            assert chars <= SPEC_TEXT_CARD_CHARS, (
                f"{where}textCard title+description {chars}자 "
                f"> {SPEC_TEXT_CARD_CHARS}자"
            )
        elif kind == "basicCard":
            chars = len(body.get("description", ""))
            assert chars <= SPEC_BASIC_CARD_CHARS, (
                f"{where}basicCard description {chars}자 > {SPEC_BASIC_CARD_CHARS}자"
            )
        elif kind == "listCard":
            items = body.get("items", [])
            assert len(items) <= SPEC_LIST_ITEMS, (
                f"{where}listCard items {len(items)}개 > {SPEC_LIST_ITEMS}개"
            )

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
        resp = KakaoResponse.basic_card("제목", "설" * 1000)
        assert_valid_skill_response(resp, "basic_card")
        desc = resp["template"]["outputs"][0]["basicCard"]["description"]
        assert len(desc) <= SPEC_BASIC_CARD_CHARS

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
