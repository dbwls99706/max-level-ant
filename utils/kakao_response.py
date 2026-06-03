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
    
    # 버튼 레이아웃 vertical 최대 노출 개수 (카카오 그룹 챗봇 가이드 표 기준)
    MAX_VERTICAL_BUTTONS = 5

    @staticmethod
    def quick_replies(
        text: str,
        replies: List[Dict]
    ) -> Dict:
        """
        빠른 응답(하단 메뉴 버튼) 포함 텍스트.

        ⚠️ 카카오 그룹(팀채팅) 챗봇은 quickReplies 컴포넌트를 지원하지 않으므로,
        본문은 simpleText 말풍선으로, 버튼은 별도 textCard 말풍선의
        buttonLayout="vertical"(최대 5개)로 노출한다.

        replies 예시:
        [
            {"label": "출석", "action": "message", "messageText": "/출석"},
            {"label": "시세", "action": "message", "messageText": "/시세 삼성전자"}
        ]
        """
        outputs: List[Dict] = [
            {
                "simpleText": {
                    "text": text
                }
            }
        ]

        if replies:
            # vertical 레이아웃은 최대 5개까지만 노출되므로 초과분은 잘라낸다
            buttons = list(replies)[: KakaoResponse.MAX_VERTICAL_BUTTONS]
            # textCard는 title/description 중 최소 하나가 필요하다.
            # 버튼 묶음 위에 한 줄짜리 안내 문구를 붙인다.
            outputs.append({
                "textCard": {
                    "description": "👇 빠른 메뉴",
                    "buttons": buttons,
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

# 빠른 응답
return KakaoResponse.quick_replies(
    text="무엇을 도와드릴까요?",
    replies=[
        {"label": "출석", "action": "message", "messageText": "/출석"},
        {"label": "잔고", "action": "message", "messageText": "/잔고"}
    ]
)
"""
