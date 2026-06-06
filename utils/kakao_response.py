"""
카카오톡 챗봇 응답 포맷 헬퍼
- 다양한 말풍선 타입 지원
"""
from typing import List, Dict, Optional


class KakaoResponse:
    """카카오톡 챗봇 응답 생성 헬퍼"""
    
    @staticmethod
    def simple_text(text: str) -> Dict:
        """
        단순 텍스트 응답
        """
        return {
            "version": "2.0",
            "template": {
                "outputs": [
                    {
                        "simpleText": {
                            "text": text
                        }
                    }
                ]
            }
        }
    
    @staticmethod
    def simple_image(image_url: str, alt_text: str = "이미지") -> Dict:
        """
        단순 이미지 응답
        """
        return {
            "version": "2.0",
            "template": {
                "outputs": [
                    {
                        "simpleImage": {
                            "imageUrl": image_url,
                            "altText": alt_text
                        }
                    }
                ]
            }
        }
    
    @staticmethod
    def basic_card(
        title: str,
        description: str,
        thumbnail_url: Optional[str] = None,
        buttons: Optional[List[Dict]] = None
    ) -> Dict:
        """
        기본 카드 응답
        
        buttons 예시:
        [
            {"action": "message", "label": "버튼1", "messageText": "/명령어"},
            {"action": "webLink", "label": "링크", "webLinkUrl": "https://..."}
        ]
        """
        card = {
            "title": title,
            "description": description
        }
        
        if thumbnail_url:
            card["thumbnail"] = {"imageUrl": thumbnail_url}
        
        if buttons:
            card["buttons"] = buttons
        
        return {
            "version": "2.0",
            "template": {
                "outputs": [
                    {
                        "basicCard": card
                    }
                ]
            }
        }
    
    @staticmethod
    def text_card(
        title: str,
        description: str,
        buttons: Optional[List[Dict]] = None
    ) -> Dict:
        """
        텍스트 카드 응답 (썸네일 없음)
        """
        card = {
            "title": title,
            "description": description
        }
        
        if buttons:
            card["buttons"] = buttons
        
        return {
            "version": "2.0",
            "template": {
                "outputs": [
                    {
                        "textCard": card
                    }
                ]
            }
        }
    
    @staticmethod
    def list_card(
        header: str,
        items: List[Dict],
        buttons: Optional[List[Dict]] = None,
        list_layout: Optional[str] = None
    ) -> Dict:
        """
        리스트 카드 응답 (팀채팅 챗봇 지원 컴포넌트)

        list_layout: "ranking" 지정 시 팀채팅 랭킹 전용 레이아웃으로 노출.
        items 예시:
        [
            {
                "title": "항목1",
                "description": "설명",
                "imageUrl": "https://...",  # 선택 (팀채팅 listCard는 이미지 불필요)
                "action": "message",
                "messageText": "/명령어"
            }
        ]
        """
        card = {
            "header": {"title": header},
            "items": items
        }

        if list_layout:
            card["listLayout"] = list_layout

        if buttons:
            card["buttons"] = buttons

        return {
            "version": "2.0",
            "template": {
                "outputs": [
                    {
                        "listCard": card
                    }
                ]
            }
        }
    
    # 버튼 레이아웃 vertical 최대 노출 개수 (카카오 그룹 챗봇 가이드 기준)
    MAX_VERTICAL_BUTTONS = 5
    # 카드 description 안전 한도. 본문은 항상 이 한도 안에서 '단일 카드'로만 노출한다.
    # (한도를 넘으면 simpleText로 쪼개지 않고, 줄 단위로 잘라 생략 표시를 붙인다.)
    CARD_DESC_LIMIT = 230

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
        - 중간 items 만 카드 한도(CARD_DESC_LIMIT)에 맞춰 앞에서부터 담는다.
        - 결과는 한도 이하가 되도록 맞춘다(초과해도 _fit_card가 한 번 더 방어).
        """
        if limit is None:
            limit = KakaoResponse.CARD_DESC_LIMIT

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
        buttons: List[Dict]
    ) -> Dict:
        """
        본문 + 액션 버튼을 함께 담은 응답.

        ⚠️ 카카오 그룹(팀채팅) 챗봇은 quickReplies 컴포넌트를 지원하지 않으므로,
        본문과 버튼을 하나의 textCard(buttonLayout="vertical", 최대 5개)로 합쳐
        노출한다. 본문은 항상 '단일 카드'로만 보내며, 카드 한도(CARD_DESC_LIMIT)를
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

        # vertical 레이아웃은 최대 5개까지만 노출되므로 초과분은 잘라낸다
        card_buttons = list(buttons)[: KakaoResponse.MAX_VERTICAL_BUTTONS]
        card_text = KakaoResponse._fit_card(text, KakaoResponse.CARD_DESC_LIMIT)

        return {
            "version": "2.0",
            "template": {
                "outputs": [
                    {
                        "textCard": {
                            "description": card_text or " ",
                            "buttons": card_buttons,
                            "buttonLayout": "vertical"
                        }
                    }
                ]
            }
        }
    
    @staticmethod
    def button_message(label: str, message_text: str) -> Dict:
        """메시지 전송 버튼 생성"""
        return {
            "action": "message",
            "label": label,
            "messageText": message_text
        }
    
    @staticmethod
    def button_link(label: str, url: str) -> Dict:
        """웹 링크 버튼 생성"""
        return {
            "action": "webLink",
            "label": label,
            "webLinkUrl": url
        }
    
    @staticmethod
    def button_share(label: str = "공유하기") -> Dict:
        """공유 버튼 생성"""
        return {
            "action": "share",
            "label": label
        }


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
