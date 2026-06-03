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
    def carousel(cards: List[Dict], card_type: str = "basicCard") -> Dict:
        """
        캐러셀 (여러 카드 슬라이드)

        card_type: "basicCard", "commerceCard", "listCard"
        """
        return {
            "version": "2.0",
            "template": {
                "outputs": [
                    {
                        "carousel": {
                            "type": card_type,
                            "items": cards
                        }
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
        buttons: Optional[List[Dict]] = None
    ) -> Dict:
        """
        리스트 카드 응답
        
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
            "items": items
        }
        
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
    # 카드 description 안전 한도. 이보다 길면 본문을 simpleText로 분리해 잘림을 방지한다.
    CARD_DESC_LIMIT = 230

    @staticmethod
    def _split_for_card(text: str, limit: int) -> tuple:
        """
        본문을 (앞부분, 카드에 담을 뒷부분)으로 나눈다.
        가능한 한 줄 단위로 끊어 카드 뒷부분이 limit 이하가 되도록 한다.
        """
        if len(text) <= limit:
            return "", text
        lines = text.split("\n")
        i = len(lines)
        tail = ""
        while i > 0:
            candidate = "\n".join(lines[i - 1:])
            if len(candidate) <= limit:
                tail = candidate
                i -= 1
            else:
                break
        head = "\n".join(lines[:i])
        if not tail:  # 줄바꿈 없는 초장문 한 줄
            head, tail = text[:-limit], text[-limit:]
        return head, tail

    @staticmethod
    def text_with_buttons(
        text: str,
        buttons: List[Dict]
    ) -> Dict:
        """
        본문 + 액션 버튼을 함께 담은 응답.

        ⚠️ 카카오 그룹(팀채팅) 챗봇은 quickReplies 컴포넌트를 지원하지 않으므로,
        본문과 버튼을 하나의 textCard(buttonLayout="vertical", 최대 5개)로 합쳐
        노출한다. 단, 본문이 카드 한도(CARD_DESC_LIMIT)보다 길면 앞부분은
        simpleText로 분리하고 뒷부분만 카드에 담아 잘림을 방지한다.

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
        head, card_text = KakaoResponse._split_for_card(
            text, KakaoResponse.CARD_DESC_LIMIT
        )

        outputs: List[Dict] = []
        if head:
            outputs.append({"simpleText": {"text": head}})
        outputs.append({
            "textCard": {
                "description": card_text or " ",
                "buttons": card_buttons,
                "buttonLayout": "vertical"
            }
        })

        return {
            "version": "2.0",
            "template": {
                "outputs": outputs
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
