"""
카카오톡 챗봇 응답 포맷 헬퍼
- 다양한 말풍선 타입 지원
"""

from typing import List, Dict, Optional

from .visual_helpers import fit_width


class KakaoResponse:
    """카카오톡 챗봇 응답 생성 헬퍼

    아래 한도는 카카오 스킬 응답 JSON 공식 명세를 따른다.
    https://kakaobusiness.gitbook.io/main/tool/chatbot/skill_guide/answer_json_format

    그룹(팀채팅) 챗봇은 대체로 일반채팅 기능의 부분집합이지만, 버튼 개수처럼
    오히려 넓어진 항목도 있다. 그런 항목은 아래에 GROUP 접미사로 따로 둔다.
    이 앱은 1:1과 그룹방을 모두 받으므로 기본값은 좁은 쪽(1:1)으로 두고,
    방을 아는 호출부만 넓은 한도를 명시적으로 넘긴다.

    미지원 컴포넌트(팀채팅): QuickReplies, CommerceCard, Carousel.
    이 셋은 만들지 않는다.
    """

    # 버튼 개수
    # - 1:1 기본 명세: 세로 3 / 가로 2
    # - 그룹 챗봇 가이드 v1.10.0: 세로 정렬은 최대 5개까지 노출
    #   (가로는 그대로 2개)
    MAX_VERTICAL_BUTTONS = 3
    MAX_VERTICAL_BUTTONS_GROUP = 5
    MAX_HORIZONTAL_BUTTONS = 2

    # 버튼 플러그인 action 타입 (그룹 챗봇 전용).
    # message/webLink처럼 별도 URL·문구 없이 동작만 지정하는 버튼들이다.
    PLUGIN_ACTIONS = frozenset(
        {
            "guide",  # 챗봇 도움말
            "share",  # 말풍선을 다른 채팅방에 공유
            "invite",  # 챗봇을 다른 채팅방에 초대
            "inviteMember",  # 현재 방에 친구 초대
            "mention",  # 입력창에 챗봇 멘션 입력
            "settings",  # 챗봇 설정(알림) 페이지
            "webViewLink",  # 주소표시줄 없는 웹뷰로 URL 열기
        }
    )

    # 한 응답에 넣을 수 있는 멘션 수 (그룹 챗봇 가이드)
    MAX_MENTIONS = 15

    # listCard items: 단일형 최대 5개
    MAX_LIST_ITEMS = 5

    # listCard 항목 한 줄 폭 (한글·이모지 = 2칸 기준).
    # 카카오가 글자 수를 막는 게 아니라 폰 화면에서 줄이 접힌다. 5줄짜리
    # 랭킹이 10줄이 되면 그룹방 화면을 통째로 덮으므로 여기서 한 줄로 맞춘다.
    LIST_ITEM_TITLE_WIDTH = 20
    LIST_ITEM_DESC_WIDTH = 24

    # template.outputs: 1개 이상 3개 이하
    MAX_OUTPUTS = 3

    # ── 스펙 상한 (초과 시 카카오가 응답을 거부할 수 있음) ──
    # simpleText: text 최대 1000자
    SIMPLE_TEXT_LIMIT = 1000
    # simpleImage: altText 최대 50자
    ALT_TEXT_LIMIT = 50
    # textCard / basicCard: title 최대 50자
    CARD_TITLE_LIMIT = 50
    # textCard: title과 description을 합쳐 최대 400자
    TEXT_CARD_LIMIT = 400
    # basicCard: description 최대 230자
    BASIC_CARD_DESC_LIMIT = 230
    # button: label 최대 14자.
    # 넘으면 카카오가 말없이 잘라내므로 "각성하기 (500,00…" 처럼
    # 정작 중요한 정보가 사라진다. 금액·횟수 같은 가변 정보는 라벨이 아니라
    # 본문에 적고, 라벨은 동작 이름만 짧게 유지한다.
    BUTTON_LABEL_LIMIT = 14

    # ── UX 한도 (스펙보다 보수적인 자체 기준) ──
    # 그룹 챗봇 beta 가이드: "챗봇 응답이 채팅창 전체를 가리지 않아야 해요.
    # 그룹 대화 맥락에 방해되지 않도록 한 화면을 가리지 않게 해주세요."
    # 스펙상 400자까지 가능하지만 그룹방 대화를 덮지 않도록 본문은 더 짧게 유지한다.
    BODY_LIMIT = 350

    @staticmethod
    def simple_text(text: str) -> Dict:
        """
        단순 텍스트 응답 (최대 1000자)
        """
        return {
            "version": "2.0",
            "template": {
                "outputs": [
                    {
                        "simpleText": {
                            "text": KakaoResponse._fit_card(
                                text, KakaoResponse.SIMPLE_TEXT_LIMIT
                            )
                        }
                    }
                ]
            },
        }

    @staticmethod
    def mention(key: str) -> str:
        """본문에 넣을 멘션 자리표시자.

        key는 이 응답 안에서만 쓰이는 임의의 이름이다. 실제 사용자는
        extra.mentions[key]가 가리킨다.
        """
        return "{{#mentions." + key + "}}"

    @staticmethod
    def simple_text_with_mentions(text: str, mentions: Dict[str, str]) -> Dict:
        """실제 사용자를 멘션하는 텍스트 응답.

        멘션은 **simpleText에서만** 동작한다(그룹 챗봇 가이드). 카드에
        넣으면 자리표시자가 그대로 노출되므로 여기서만 만든다.
        버튼을 함께 주고 싶으면 두 번째 output에 카드로 붙여야 한다.

        mentions: {자리표시자 키: botUserKey}
            botUserKey는 SkillRequest의 userRequest.user.id 값이다.

        본문에 등장하지 않는 키는 버린다. extra에 남겨두면 카카오가
        치환할 대상을 못 찾고, 무엇보다 '누구를 부르려 했는지'가
        응답과 어긋난 채 남는다.
        """
        text = KakaoResponse._fit_card(text, KakaoResponse.SIMPLE_TEXT_LIMIT)

        used = {}
        for key, user_id in mentions.items():
            if not user_id:
                continue
            if KakaoResponse.mention(key) not in text:
                continue
            used[key] = user_id
            if len(used) >= KakaoResponse.MAX_MENTIONS:
                break

        resp = {
            "version": "2.0",
            "template": {"outputs": [{"simpleText": {"text": text}}]},
        }
        if used:
            resp["extra"] = {
                "mentions": {
                    key: {"type": "botUserKey", "id": user_id}
                    for key, user_id in used.items()
                }
            }
        return resp

    @staticmethod
    def simple_image(image_url: str, alt_text: str = "이미지") -> Dict:
        """
        단순 이미지 응답 (altText 최대 50자)
        """
        return {
            "version": "2.0",
            "template": {
                "outputs": [
                    {
                        "simpleImage": {
                            "imageUrl": image_url,
                            "altText": (alt_text or "")[: KakaoResponse.ALT_TEXT_LIMIT],
                        }
                    }
                ]
            },
        }

    @staticmethod
    def basic_card(
        title: str,
        description: str,
        thumbnail_url: str,
        buttons: Optional[List[Dict]] = None,
        button_cap: Optional[int] = None,
    ) -> Dict:
        """
        기본 카드 응답 (피드형)

        thumbnail은 카카오 명세상 **필수**이므로 인자로 강제한다.
        title 최대 50자, description 최대 230자.

        buttons 예시:
        [
            {"action": "message", "label": "버튼1", "messageText": "/명령어"},
            {"action": "webLink", "label": "링크", "webLinkUrl": "https://..."}
        ]
        """
        if not thumbnail_url:
            raise ValueError("basicCard는 thumbnail이 필수입니다")

        card = {
            "title": (title or "")[: KakaoResponse.CARD_TITLE_LIMIT],
            "description": KakaoResponse._fit_card(
                description, KakaoResponse.BASIC_CARD_DESC_LIMIT
            ),
            "thumbnail": {"imageUrl": thumbnail_url},
        }

        if buttons:
            card["buttons"] = KakaoResponse._fit_buttons(buttons, button_cap=button_cap)

        return {"version": "2.0", "template": {"outputs": [{"basicCard": card}]}}

    @staticmethod
    def text_card(
        title: str,
        description: str,
        buttons: Optional[List[Dict]] = None,
        button_cap: Optional[int] = None,
    ) -> Dict:
        """
        텍스트 카드 응답 (썸네일 없음)

        textCard는 title 최대 50자이고, title+description 합산 400자 한도다.
        title이 차지한 만큼을 빼고 description을 맞춘다.
        title/description 중 최소 하나는 있어야 한다.
        """
        title = (title or "")[: KakaoResponse.CARD_TITLE_LIMIT]
        budget = max(0, KakaoResponse.TEXT_CARD_LIMIT - len(title))
        description = KakaoResponse._fit_card(description or "", budget)
        if not title and not description:
            raise ValueError("textCard는 title과 description 중 하나가 필요합니다")

        card = {"description": description}
        if title:
            card["title"] = title

        if buttons:
            card["buttons"] = KakaoResponse._fit_buttons(buttons, button_cap=button_cap)

        return {"version": "2.0", "template": {"outputs": [{"textCard": card}]}}

    @staticmethod
    def list_card(
        header: str,
        items: List[Dict],
        buttons: Optional[List[Dict]] = None,
        list_layout: Optional[str] = None,
        button_cap: Optional[int] = None,
    ) -> Dict:
        """
        리스트 카드 응답

        list_layout="ranking": 그룹(팀채팅) 챗봇 전용 '리스트(랭킹)' 말풍선.
        그룹 챗봇 스킬 서버 가이드 v1.11.1이 `"listLayout": "ranking"` 필드와
        JSON 예제를 명시한다. 필드 이름까지 확인된 값이다.
        (그래도 렌더링 실패 시 이 인자만 빼면 일반 리스트로 정상 노출된다.)

        items 예시:
        [
            {
                "title": "항목1",
                "description": "설명",
                "imageUrl": "https://...",  # 선택
                "action": "message",
                "messageText": "/명령어"
            }
        ]
        """
        card = {
            "header": {"title": header},
            "items": [
                KakaoResponse._fit_item(i)
                for i in list(items)[: KakaoResponse.MAX_LIST_ITEMS]
            ],
        }

        if list_layout:
            card["listLayout"] = list_layout

        if buttons:
            card["buttons"] = KakaoResponse._fit_buttons(buttons, button_cap=button_cap)

        return {"version": "2.0", "template": {"outputs": [{"listCard": card}]}}

    @staticmethod
    def _fit_item(item: Dict) -> Dict:
        """listCard 항목을 한 줄에 맞춘다 (원본 dict은 건드리지 않는다).

        길이가 아니라 '표시 폭'으로 자른다. 한글은 두 칸이라 글자 수로
        재면 실제보다 절반으로 착각한다.
        """
        fitted = dict(item)
        if isinstance(fitted.get("title"), str):
            fitted["title"] = fit_width(
                fitted["title"], KakaoResponse.LIST_ITEM_TITLE_WIDTH
            )
        if isinstance(fitted.get("description"), str):
            fitted["description"] = fit_width(
                fitted["description"], KakaoResponse.LIST_ITEM_DESC_WIDTH
            )
        return fitted

    @staticmethod
    def _fit_buttons(
        buttons: List[Dict],
        layout: str = "vertical",
        button_cap: Optional[int] = None,
    ) -> List[Dict]:
        """
        버튼을 스펙에 맞춘다.
          - 개수: 레이아웃 한도(세로 3, 그룹방은 5 / 가로 2)까지만
          - 라벨: 14자 한도. 넘으면 카카오가 말없이 잘라 뒤가 사라지므로,
            여기서 잘라 최소한 잘렸다는 표시(…)라도 남긴다.

        button_cap: 세로 정렬일 때만 쓰이는 상한. 그룹방을 아는 호출부가
            MAX_VERTICAL_BUTTONS_GROUP을 넘긴다. 가로 정렬은 그룹에서도
            2개가 상한이라 이 값을 무시한다.
        """
        if layout == "vertical":
            cap = button_cap or KakaoResponse.MAX_VERTICAL_BUTTONS
            cap = min(cap, KakaoResponse.MAX_VERTICAL_BUTTONS_GROUP)
        else:
            cap = KakaoResponse.MAX_HORIZONTAL_BUTTONS
        return [KakaoResponse._fit_label(b) for b in list(buttons)[:cap]]

    @staticmethod
    def _fit_label(button: Dict) -> Dict:
        """버튼 라벨을 14자 한도로 맞춘다 (원본 dict은 건드리지 않는다)"""
        label = button.get("label")
        if not isinstance(label, str) or len(label) <= KakaoResponse.BUTTON_LABEL_LIMIT:
            return button
        trimmed = dict(button)
        trimmed["label"] = label[: KakaoResponse.BUTTON_LABEL_LIMIT - 1] + "…"
        return trimmed

    @staticmethod
    def _fit_card(text: str, limit: int) -> str:
        """
        본문을 카드 한 장(limit) 안에 들어오도록 줄 단위로 자른다.
        잘리면 끝에 생략 표시를 붙인다. 본문은 절대 다른 말풍선으로 분리하지 않는다.
        """
        if len(text) <= limit:
            return text
        marker = "\n…(생략)"
        budget = max(0, limit - len(marker))
        lines = text.split("\n")
        kept: List[str] = []
        used = 0
        for ln in lines:
            add = len(ln) + (1 if kept else 0)
            if used + add > budget:
                break
            kept.append(ln)
            used += add
        fitted = "\n".join(kept)
        if not fitted:  # 첫 줄이 한도보다 긴 경우 강제로 자른다
            fitted = text[:budget]
        return fitted + marker

    @staticmethod
    def fit_items(
        header: str,
        items: List[str],
        footer: str = "",
        limit: Optional[int] = None,
        more_fmt: str = "…외 {n}개 더",
    ) -> str:
        """
        헤더 + (한도 안에 들어가는 만큼의 항목) + (생략 시 '…외 N개 더') + 푸터를
        하나의 카드 본문 문자열로 조립한다.

        - header/footer 는 항상 유지된다(예: 총자산·내 순위 같은 요약은 잘리지 않음).
        - 중간 items 만 본문 한도(BODY_LIMIT)에 맞춰 앞에서부터 담는다.
        - 결과는 한도 이하가 되도록 맞춘다(초과해도 _fit_card가 한 번 더 방어).
        """
        if limit is None:
            limit = KakaoResponse.BODY_LIMIT

        def join(parts: List[str]) -> str:
            return "\n".join(p for p in parts if p)

        tail = [footer] if footer else []

        full = join([header] + items + tail)
        if len(full) <= limit:
            return full

        # 생략 표시가 차지할 공간을 미리 예약하고 앞에서부터 담는다
        reserve = len(more_fmt.format(n=len(items)))
        kept: List[str] = []
        for it in items:
            candidate = join([header] + kept + [it] + tail)
            if len(candidate) + reserve > limit:
                break
            kept.append(it)

        dropped = len(items) - len(kept)
        more = [more_fmt.format(n=dropped)] if dropped > 0 else []
        return join([header] + kept + more + tail)

    @staticmethod
    def text_with_buttons(
        text: str,
        buttons: List[Dict],
        button_cap: Optional[int] = None,
        force_vertical: bool = False,
    ) -> Dict:
        """
        본문 + 액션 버튼을 함께 담은 응답.

        ⚠️ 카카오 그룹(팀채팅) 챗봇은 quickReplies 컴포넌트를 지원하지 않으므로,
        본문과 버튼을 하나의 textCard로 합쳐 노출한다.
        기본은 가로 2개다(넘치는 버튼은 잘린다). 세 개 이상을 반드시
        보여야 하는 화면만 force_vertical=True로 세로 배치를 요청한다.
        세로 한도는 1:1이 3개, 그룹방이 5개다(button_cap으로 지정).
        본문은 항상 '단일 카드'로만 보내며, 카드 한도(TEXT_CARD_LIMIT)를
        넘으면 줄 단위로 잘라 생략 표시를 붙인다(본문을 별도 말풍선으로 쪼개지 않음).
        길이가 가변적인 목록은 핸들러에서 fit_items()로 미리 줄여 보내는 것을 권장한다.

        buttons 예시:
        [
            {"label": "출석", "action": "message", "messageText": "/출석"},
            {"label": "시세", "action": "message", "messageText": "/시세 삼성전자"}
        ]
        """
        if not buttons:
            return {
                "version": "2.0",
                "template": {"outputs": [{"simpleText": {"text": text}}]},
            }

        # 기본은 가로 2개다. 세로로 쌓으면 버튼 하나가 한 줄씩 먹어서
        # 그룹방 대화창을 그만큼 가린다. 선택지를 두 개로 좁히는 편이
        # 화면도 아끼고 다음 행동도 분명해진다.
        # 정말 더 필요한 화면만 layout="vertical"을 명시한다.
        layout = "vertical" if force_vertical else "horizontal"
        card_buttons = KakaoResponse._fit_buttons(buttons, layout, button_cap)
        # title이 없으므로 스펙상 400자까지 가능하지만, 그룹방 화면을 덮지 않도록
        # 더 보수적인 BODY_LIMIT을 적용한다.
        card_text = KakaoResponse._fit_card(text, KakaoResponse.BODY_LIMIT)

        return {
            "version": "2.0",
            "template": {
                "outputs": [
                    {
                        "textCard": {
                            "description": card_text or " ",
                            "buttons": card_buttons,
                            "buttonLayout": layout,
                        }
                    }
                ]
            },
        }

    @staticmethod
    def button_message(label: str, message_text: str) -> Dict:
        """메시지 전송 버튼 생성"""
        return {"action": "message", "label": label, "messageText": message_text}

    @staticmethod
    def button_link(label: str, url: str) -> Dict:
        """웹 링크 버튼 생성"""
        return {"action": "webLink", "label": label, "webLinkUrl": url}

    @staticmethod
    def button_share(label: str = "공유하기") -> Dict:
        """공유 버튼 생성"""
        return {"action": "share", "label": label}


# 사용 예시
"""
# 단순 텍스트
return KakaoResponse.simple_text("안녕하세요!")

# 버튼이 있는 카드
return KakaoResponse.basic_card(
    title="삼성전자",
    description="현재가: 58,200원\\n전일대비: +1.2%",
    buttons=[
        KakaoResponse.button_message("매수하기", "/매수 삼성전자"),
        KakaoResponse.button_message("매도하기", "/매도 삼성전자")
    ]
)

# 본문 + 버튼 (그룹챗봇: textCard 버튼으로 노출)
return KakaoResponse.text_with_buttons(
    text="무엇을 도와드릴까요?",
    buttons=[
        {"label": "출석", "action": "message", "messageText": "/출석"},
        {"label": "잔고", "action": "message", "messageText": "/잔고"}
    ]
)
"""
