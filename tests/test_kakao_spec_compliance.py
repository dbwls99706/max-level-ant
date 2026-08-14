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
- 버튼: 세로 3 / 가로 2, label 최대 14자

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
# 그룹(팀채팅) 챗봇 스킬 서버 가이드 v1.10.0:
# buttonLayout이 vertical이면 최대 5개까지 노출된다.
SPEC_BUTTONS_VERTICAL_GROUP = 5
SPEC_BUTTONS_HORIZONTAL = 2

# 팀채팅 챗봇이 지원하지 않는 컴포넌트. 만들면 응답 자체가 안 그려진다.
UNSUPPORTED_COMPONENTS = {"quickReplies", "commerceCard", "carousel"}
SPEC_BUTTON_LABEL_CHARS = 14


def assert_valid_skill_response(resp: dict, label: str = "", in_group: bool = False):
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
        elif kind in UNSUPPORTED_COMPONENTS:
            raise AssertionError(f"{where}팀채팅에서 지원하지 않는 컴포넌트: {kind}")
        else:
            raise AssertionError(f"{where}알 수 없는 컴포넌트: {kind}")

        buttons = body.get("buttons") or []
        layout = body.get("buttonLayout", "vertical")
        if layout == "vertical":
            cap = SPEC_BUTTONS_VERTICAL_GROUP if in_group else SPEC_BUTTONS_VERTICAL
        else:
            cap = SPEC_BUTTONS_HORIZONTAL
        assert len(buttons) <= cap, (
            f"{where}{kind} 버튼 {len(buttons)}개 > {layout} 한도 {cap}개"
        )
        for btn in buttons:
            assert "label" in btn and "action" in btn, f"{where}버튼 필드 누락: {btn}"
            btn_label = btn.get("label", "")
            assert len(btn_label) <= SPEC_BUTTON_LABEL_CHARS, (
                f"{where}버튼 라벨 {len(btn_label)}자 > {SPEC_BUTTON_LABEL_CHARS}자: "
                f"{btn_label!r} — 카카오가 말없이 잘라 뒷부분이 사라진다"
            )


class TestComponentLimits:
    """헬퍼가 스펙 한도를 강제하는지"""

    def test_text_with_buttons_caps_buttons(self):
        btns = [
            {"label": f"B{i}", "action": "message", "messageText": f"/{i}"}
            for i in range(10)
        ]
        resp = KakaoResponse.text_with_buttons("본문", btns)
        assert_valid_skill_response(resp, "text_with_buttons")

    def test_two_buttons_use_horizontal_layout(self):
        """
        버튼 2개는 가로로 배치한다. 짧은 라벨을 세로로 쌓으면
        응답 높이만 늘어나 그룹방 대화창을 가린다.
        """
        btns = [
            {
                "label": "💼 포트폴리오",
                "action": "message",
                "messageText": "/포트폴리오",
            },
            {"label": "📈 인기종목", "action": "message", "messageText": "/인기"},
        ]
        resp = KakaoResponse.text_with_buttons("본문", btns)
        assert_valid_skill_response(resp, "2 buttons")

        card = resp["template"]["outputs"][0]["textCard"]
        assert card["buttonLayout"] == "horizontal"
        assert len(card["buttons"]) == 2, "가로 배치에서 버튼이 잘리면 안 된다"

    @pytest.mark.parametrize("count", [1, 2, 3, 5])
    def test_horizontal_is_the_default(self, count):
        """기본은 가로 2개다.

        세로로 쌓으면 버튼 하나가 한 줄씩 먹어 그룹방 대화창을 그만큼
        가린다. 선택지를 둘로 좁히는 편이 화면도 아끼고 다음 행동도
        분명해진다. 셋 이상이 꼭 필요한 화면만 force_vertical을 쓴다.
        """
        btns = [
            {"label": f"버튼{i}", "action": "message", "messageText": f"/{i}"}
            for i in range(count)
        ]
        resp = KakaoResponse.text_with_buttons("본문", btns)
        assert_valid_skill_response(resp, f"{count} buttons")

        card = resp["template"]["outputs"][0]["textCard"]
        assert card["buttonLayout"] == "horizontal"
        assert len(card["buttons"]) == min(count, SPEC_BUTTONS_HORIZONTAL)

    def test_force_vertical_opts_out(self):
        """정말 셋 이상이 필요한 화면은 명시적으로 세로를 요청한다"""
        btns = [
            {"label": f"버튼{i}", "action": "message", "messageText": f"/{i}"}
            for i in range(3)
        ]
        resp = KakaoResponse.text_with_buttons("본문", btns, force_vertical=True)
        card = resp["template"]["outputs"][0]["textCard"]
        assert card["buttonLayout"] == "vertical"
        assert len(card["buttons"]) == 3

    def test_extra_buttons_are_dropped_not_wrapped(self):
        """가로 한도를 넘는 버튼은 잘린다.

        핸들러가 버튼을 셋 이상 넘기면 앞의 두 개만 남는다는 뜻이므로,
        가장 중요한 행동을 앞에 두어야 한다.
        """
        btns = [
            {"label": f"버튼{i}", "action": "message", "messageText": f"/{i}"}
            for i in range(4)
        ]
        card = KakaoResponse.text_with_buttons("본문", btns)["template"]["outputs"][0][
            "textCard"
        ]
        assert card["buttonLayout"] == "horizontal"
        assert [b["label"] for b in card["buttons"]] == ["버튼0", "버튼1"]
        assert len(card["buttons"]) == SPEC_BUTTONS_HORIZONTAL

    def test_long_button_label_is_trimmed(self):
        """
        14자를 넘는 라벨은 헬퍼가 잘라야 한다.

        그대로 두면 카카오가 말없이 잘라 "각성하기 (500,00…"처럼
        정작 중요한 정보가 사라진다.
        """
        btns = [
            {
                "label": "🧬 각성하기 (5,000,000원)",
                "action": "message",
                "messageText": "/각성 시도",
            }
        ]
        resp = KakaoResponse.text_with_buttons("본문", btns)
        assert_valid_skill_response(resp, "long label")

        out = resp["template"]["outputs"][0]
        rendered = next(iter(out.values()))["buttons"][0]["label"]
        assert len(rendered) <= SPEC_BUTTON_LABEL_CHARS
        assert rendered.endswith("…"), "잘렸다는 표시가 없다"

    def test_button_label_at_limit_is_untouched(self):
        """정확히 14자면 손대지 않는다 (경계값)"""
        exact = "가" * SPEC_BUTTON_LABEL_CHARS
        resp = KakaoResponse.text_with_buttons(
            "본문", [{"label": exact, "action": "message", "messageText": "/x"}]
        )
        out = resp["template"]["outputs"][0]
        assert next(iter(out.values()))["buttons"][0]["label"] == exact

    def test_trimming_does_not_mutate_caller_dict(self):
        """호출부가 넘긴 dict을 그대로 바꿔버리면 안 된다"""
        original = {
            "label": "🧬 각성하기 (5,000,000원)",
            "action": "message",
            "messageText": "/각성 시도",
        }
        KakaoResponse.text_with_buttons("본문", [original])
        assert original["label"] == "🧬 각성하기 (5,000,000원)"

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
        assert_valid_skill_response(
            resp, f"group:{command or '(빈 발화)'}", in_group=True
        )


class TestGroupButtonAllowance:
    """그룹방에서만 넓어지는 버튼 한도"""

    def _buttons(self, n):
        return [
            {"label": f"B{i}", "action": "message", "messageText": f"/{i}"}
            for i in range(n)
        ]

    def test_one_to_one_still_caps_at_three(self):
        """1:1 기본 명세는 여전히 3개다. 넓은 한도를 기본값으로 두면 안 된다"""
        resp = KakaoResponse.text_with_buttons(
            "본문", self._buttons(5), force_vertical=True
        )
        assert_valid_skill_response(resp, "1:1 버튼")
        assert len(resp["template"]["outputs"][0]["textCard"]["buttons"]) == 3

    def test_group_allows_five(self):
        resp = KakaoResponse.text_with_buttons(
            "본문",
            self._buttons(7),
            button_cap=KakaoResponse.MAX_VERTICAL_BUTTONS_GROUP,
            force_vertical=True,
        )
        assert_valid_skill_response(resp, "그룹 버튼", in_group=True)
        assert len(resp["template"]["outputs"][0]["textCard"]["buttons"]) == 5

    def test_group_cap_never_exceeds_spec(self):
        """호출부가 과한 값을 넘겨도 스펙을 넘지 않아야 한다"""
        resp = KakaoResponse.text_with_buttons(
            "본문", self._buttons(9), button_cap=99, force_vertical=True
        )
        assert_valid_skill_response(resp, "과한 cap", in_group=True)
        assert (
            len(resp["template"]["outputs"][0]["textCard"]["buttons"])
            == SPEC_BUTTONS_VERTICAL_GROUP
        )

    def test_horizontal_stays_two_even_in_group(self):
        """가로 정렬은 그룹에서도 2개가 상한이다.

        text_with_buttons는 버튼이 정확히 2개일 때만 가로로 배치하므로,
        상한이 지켜지는지는 _fit_buttons를 직접 불러 확인해야 한다.
        (2개만 넘기면 cap이 3이든 5든 결과가 같아 구분이 안 된다.)
        """
        fitted = KakaoResponse._fit_buttons(
            self._buttons(5), layout="horizontal", button_cap=5
        )
        assert len(fitted) == SPEC_BUTTONS_HORIZONTAL

    def test_horizontal_layout_is_chosen_for_two(self):
        resp = KakaoResponse.text_with_buttons("본문", self._buttons(2), button_cap=5)
        card = resp["template"]["outputs"][0]["textCard"]
        assert card["buttonLayout"] == "horizontal"
        assert len(card["buttons"]) == SPEC_BUTTONS_HORIZONTAL

    def test_handler_cap_follows_the_room(self, db, test_user):
        """핸들러가 방 종류에 따라 한도를 고른다"""
        from handlers import CommandHandler

        solo = CommandHandler(db, test_user.kakao_id, "/각성", "테스터", "")
        group = CommandHandler(db, test_user.kakao_id, "/각성", "테스터", "gk-1")
        assert solo.button_cap == SPEC_BUTTONS_VERTICAL
        assert group.button_cap == SPEC_BUTTONS_VERTICAL_GROUP


class TestPluginButtons:
    """그룹 챗봇 버튼 플러그인 (guide/share/invite 등)"""

    def test_plugin_buttons_survive_the_fitter(self):
        """messageText나 URL이 없어도 버튼이 유지돼야 한다"""
        buttons = [
            {"label": "도움말", "action": "guide"},
            {"label": "공유하기", "action": "share"},
        ]
        resp = KakaoResponse.text_with_buttons("본문", buttons)
        assert_valid_skill_response(resp, "플러그인 버튼")
        actions = [
            b["action"] for b in resp["template"]["outputs"][0]["textCard"]["buttons"]
        ]
        assert actions == ["guide", "share"]

    def test_declared_plugin_actions_are_known(self):
        """가이드에 있는 action 타입이 상수에 다 들어 있어야 한다"""
        documented = {
            "guide",
            "share",
            "invite",
            "inviteMember",
            "mention",
            "settings",
            "webViewLink",
        }
        assert documented == set(KakaoResponse.PLUGIN_ACTIONS)


class TestUnsupportedComponents:
    """팀채팅이 지원하지 않는 컴포넌트를 만들지 않는지"""

    @pytest.mark.parametrize("kind", sorted(UNSUPPORTED_COMPONENTS))
    def test_unsupported_component_is_rejected(self, kind):
        """검사기가 이걸 못 잡으면 응답이 통째로 안 그려지는 걸 배포까지 모른다"""
        resp = {"version": "2.0", "template": {"outputs": [{kind: {}}]}}
        with pytest.raises(AssertionError, match="지원하지 않는"):
            assert_valid_skill_response(resp, kind)

    def test_builders_never_emit_them(self):
        """헬퍼가 만드는 응답에는 미지원 컴포넌트가 없어야 한다"""
        made = [
            KakaoResponse.simple_text("본문"),
            KakaoResponse.text_card("제목", "설명"),
            KakaoResponse.basic_card("제목", "설명", "https://img/x.png"),
            KakaoResponse.list_card("헤더", [{"title": "항목"}]),
            KakaoResponse.simple_image("https://img/x.png", "alt"),
            KakaoResponse.text_with_buttons("본문", []),
        ]
        for resp in made:
            for out in resp["template"]["outputs"]:
                assert not (set(out) & UNSUPPORTED_COMPONENTS), out


class TestMentions:
    """실제 사용자 멘션 (그룹 챗봇 전용, simpleText에서만 동작)"""

    def test_mention_token_format(self):
        assert KakaoResponse.mention("u1") == "{{#mentions.u1}}"

    def test_mentions_land_in_extra(self):
        text = f"1위 {KakaoResponse.mention('u1')}"
        resp = KakaoResponse.simple_text_with_mentions(text, {"u1": "bu-aaa"})
        assert_valid_skill_response(resp, "멘션", in_group=True)
        assert resp["extra"]["mentions"]["u1"] == {
            "type": "botUserKey",
            "id": "bu-aaa",
        }

    def test_unused_keys_are_dropped(self):
        """본문에 없는 키를 extra에 남기면 응답과 의도가 어긋난 채로 나간다"""
        text = f"1위 {KakaoResponse.mention('u1')}"
        resp = KakaoResponse.simple_text_with_mentions(
            text, {"u1": "bu-aaa", "ghost": "bu-zzz"}
        )
        assert set(resp["extra"]["mentions"]) == {"u1"}

    def test_empty_user_id_is_dropped(self):
        text = f"1위 {KakaoResponse.mention('u1')}"
        resp = KakaoResponse.simple_text_with_mentions(text, {"u1": ""})
        assert "extra" not in resp

    def test_no_mentions_means_no_extra_key(self):
        resp = KakaoResponse.simple_text_with_mentions("멘션 없음", {})
        assert_valid_skill_response(resp, "멘션 없음")
        assert "extra" not in resp

    def test_mention_count_is_capped(self):
        """한 응답에 15명이 상한이다. 넘기면 카카오가 응답을 거부할 수 있다"""
        keys = [f"u{i}" for i in range(30)]
        text = " ".join(KakaoResponse.mention(k) for k in keys)
        resp = KakaoResponse.simple_text_with_mentions(
            text, {k: f"bu-{k}" for k in keys}
        )
        assert len(resp["extra"]["mentions"]) == KakaoResponse.MAX_MENTIONS

    def test_only_simple_text_carries_mentions(self):
        """카드에 자리표시자를 넣으면 치환되지 않고 그대로 노출된다"""
        text = f"1위 {KakaoResponse.mention('u1')}"
        resp = KakaoResponse.simple_text_with_mentions(text, {"u1": "bu-aaa"})
        kind = next(iter(resp["template"]["outputs"][0]))
        assert kind == "simpleText"


class TestListItemWidth:
    """listCard 항목이 폰에서 한 줄에 들어가는지

    카카오는 글자 수를 막지 않는다. 대신 폰 화면에서 줄이 접히고,
    5줄짜리 랭킹이 10줄이 되어 그룹방 화면을 통째로 덮는다.
    한글·이모지는 두 칸을 차지하므로 len()이 아니라 표시 폭으로 잰다.
    """

    def _items(self, resp):
        for out in resp["template"]["outputs"]:
            card = out.get("listCard")
            if card:
                yield from card["items"]

    def test_display_width_counts_wide_chars_as_two(self):
        """폭 계산 자체를 값으로 못박는다.

        다른 테스트는 display_width로 재기 때문에, 이 함수가 len()으로
        바뀌면 재는 쪽과 재어지는 쪽이 함께 틀려서 아무도 못 잡는다.
        """
        from utils import display_width

        assert display_width("abc") == 3
        assert display_width("가나다") == 6, "한글은 두 칸이다"
        assert display_width("📈") == 2, "이모지는 두 칸이다"
        assert display_width("가a") == 3
        assert display_width("") == 0

    def test_fit_width_keeps_the_budget(self):
        from utils import display_width, fit_width

        for limit in (4, 8, 12, 20):
            out = fit_width("가나다라마바사아자차", limit)
            assert display_width(out) <= limit, (limit, out)

    def test_fit_width_leaves_short_text_alone(self):
        from utils import fit_width

        assert fit_width("짧다", 20) == "짧다"

    def test_helper_fits_long_items(self):
        from utils import display_width

        items = [
            {
                "title": "🥇 아주아주긴닉네임을가진사람",
                "description": "📈 +12.34% (+1,234,000원) · 🧬Lv.30 · 추가정보",
            }
        ]
        resp = KakaoResponse.list_card("헤더", items)
        for item in self._items(resp):
            assert display_width(item["title"]) <= KakaoResponse.LIST_ITEM_TITLE_WIDTH
            assert (
                display_width(item["description"]) <= KakaoResponse.LIST_ITEM_DESC_WIDTH
            )

    def test_ranking_items_fit_one_line(self, db):
        """실제 랭킹 응답이 한 줄에 들어가야 한다"""
        from utils import display_width
        from handlers import CommandHandler
        from models import ChatRoomMember, User

        group_key = "width-room"
        rows = [
            ("w1", "유진", 12_340_000, 30, "myth"),
            ("w2", "김지훈아주긴닉네임", 11_000_000, 14, "epic"),
            ("w3", "하나", 9_000_000, 0, None),
        ]
        for uid, name, cash, lv, rarity in rows:
            db.add(
                User(
                    kakao_id=uid,
                    nickname=name,
                    cash=cash,
                    initial_cash=10_000_000,
                    enhance_level=lv,
                    enhance_rarity=rarity,
                )
            )
            db.add(ChatRoomMember(group_key=group_key, kakao_id=uid))
        db.commit()

        resp = CommandHandler(db, "w1", "/랭킹", "유진", group_key).handle()
        assert_valid_skill_response(resp, "/랭킹", in_group=True)

        items = list(self._items(resp))
        assert items, "랭킹이 listCard로 나오지 않았다"
        for item in items:
            title, desc = item["title"], item.get("description", "")
            assert display_width(title) <= KakaoResponse.LIST_ITEM_TITLE_WIDTH, (
                f"제목이 한 줄을 넘는다: {title}"
            )
            assert display_width(desc) <= KakaoResponse.LIST_ITEM_DESC_WIDTH, (
                f"설명이 한 줄을 넘는다: {desc}"
            )
            # 폭만 재면 _fit_item이 잘라준 덕에 항상 통과한다.
            # 정작 잡아야 하는 건 '핸들러가 한 줄에 안 들어갈 문구를 만들어
            # 잘려나갔다'는 사실이다. 잘림 표시가 남았는지로 확인한다.
            assert not desc.endswith("…"), f"설명이 잘렸다(정보 손실): {desc}"

    def test_rank_markers_survive_a_long_nickname(self):
        """닉네임이 길어도 종·본인 표시가 먼저 잘리면 안 된다"""
        from handlers.social_handler import SocialHandlerMixin

        title = SocialHandlerMixin._rank_title("🥇", "아주아주아주긴닉네임", "🟨⭐")
        assert title.endswith("🟨⭐"), f"마커가 잘렸다: {title}"
