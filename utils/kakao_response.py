"""
카카오톡 챗봇 응답 포맷 헬퍼
- 다양한 말풍선 타입 지원
"""

from typing import List, Dict, Optional


class KakaoResponse:
    """카카오톡 챗봇 응답 생성 헬퍼

    아래 한도는 카카오 스킬 응답 JSON 공식 명세를 따른다.
    https://kakaobusiness.gitbook.io/main/tool/chatbot/skill_guide/answer_json_format

    그룹(팀채팅) 챗봇은 일반채팅에 제공되는 기능의 부분집합이므로,
    표준 명세보다 넉넉한 한도를 가정하지 않는다.
    """

    # 버튼 개수: 세로 정렬 최대 3개, 가로 정렬 최대 2개
    MAX_VERTICAL_BUTTONS = 3
    MAX_HORIZONTAL_BUTTONS = 2

    # listCard items: 단일형 최대 5개
    MAX_LIST_ITEMS = 5

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
            card["buttons"] = KakaoResponse._fit_buttons(buttons)

        return {"version": "2.0", "template": {"outputs": [{"basicCard": card}]}}

    @staticmethod
    def text_card(
        title: str, description: str, buttons: Optional[List[Dict]] = None
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
            card["buttons"] = KakaoResponse._fit_buttons(buttons)

        return {"version": "2.0", "template": {"outputs": [{"textCard": card}]}}

    @staticmethod
    def list_card(
        header: str,
        items: List[Dict],
        buttons: Optional[List[Dict]] = None,
        list_layout: Optional[str] = None,
    ) -> Dict:
        """
        리스트 카드 응답

        list_layout="ranking": 그룹(팀채팅) 챗봇 전용 '리스트(랭킹)' 말풍선.

        ⚠️ 검증 상태: 그룹 챗봇 beta 가이드 슬라이드 32는 사용 가능한 말풍선으로
        텍스트 / 텍스트(링크) / 이미지 / 리스트 / 피드 / **리스트(랭킹)**을 명시한다.
        즉 '랭킹 리스트 말풍선이 존재한다'는 것까지는 확인됐다.
        다만 그 말풍선을 지정하는 JSON 필드가 정확히 `listLayout: "ranking"`인지는
        공개 기본 명세에 없고 beta 문서의 JSON 예제로도 확인하지 못했다.
        개발 채널에서 실제 렌더링을 확인하기 전까지는 미검증 상태로 둔다.
        (렌더링 실패 시 이 인자만 빼면 일반 리스트로 정상 노출된다.)

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
            "items": list(items)[: KakaoResponse.MAX_LIST_ITEMS],
        }

        if list_layout:
            card["listLayout"] = list_layout

        if buttons:
            card["buttons"] = KakaoResponse._fit_buttons(buttons)

        return {"version": "2.0", "template": {"outputs": [{"listCard": card}]}}

    @staticmethod
    def _fit_buttons(buttons: List[Dict], layout: str = "vertical") -> List[Dict]:
        """버튼 개수를 레이아웃 한도(세로 3 / 가로 2)에 맞춰 자른다"""
        cap = (
            KakaoResponse.MAX_VERTICAL_BUTTONS
            if layout == "vertical"
            else KakaoResponse.MAX_HORIZONTAL_BUTTONS
        )
        return list(buttons)[:cap]

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
    def text_with_buttons(text: str, buttons: List[Dict]) -> Dict:
        """
        본문 + 액션 버튼을 함께 담은 응답.

        ⚠️ 카카오 그룹(팀채팅) 챗봇은 quickReplies 컴포넌트를 지원하지 않으므로,
        본문과 버튼을 하나의 textCard(buttonLayout="vertical", 최대 3개)로 합쳐
        노출한다. 본문은 항상 '단일 카드'로만 보내며, 카드 한도(TEXT_CARD_LIMIT)를
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

        # vertical 레이아웃은 최대 3개까지만 노출되므로 초과분은 잘라낸다
        card_buttons = KakaoResponse._fit_buttons(buttons, "vertical")
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
                            "buttonLayout": "vertical",
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
