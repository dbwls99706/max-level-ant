"""
기본 핸들러 믹스인
- 공통 기능 제공
"""
from typing import Dict
from sqlalchemy.orm import Session

from config import is_market_closed
from utils import get_handler_logger

logger = get_handler_logger()


class BaseHandlerMixin:
    """핸들러 공통 기능"""

    db: Session
    kakao_id: str
    utterance: str
    nickname: str

    def _get_game_buttons(self) -> list:
        """장 마감 시간에만 게임 버튼 반환 (복권 제외 - 중복 방지)"""
        if is_market_closed():
            return [
                {"label": "🎰 게임", "action": "message", "messageText": "/게임"}
            ]
        return []

    def _parse_parts(self, min_parts: int = 2) -> tuple:
        """
        명령어 파싱
        Returns: (parts, is_valid)
        """
        parts = self.utterance.split()
        if len(parts) < min_parts:
            return parts, False
        return parts, True

    def _parse_with_amount(self) -> tuple:
        """
        금액이 포함된 명령어 파싱
        예: /슬롯머신 50000
        Returns: (command, amount, is_valid)
        """
        parts = self.utterance.split()
        if len(parts) < 2:
            return parts[0] if parts else "", None, False

        try:
            amount = int(parts[1].replace(",", ""))
            return parts[0], amount, True
        except ValueError:
            return parts[0], None, False

    def _parse_with_choice(self) -> tuple:
        """
        금액과 선택이 포함된 명령어 파싱
        예: /동전 50000 앞
        Returns: (command, amount, choice, is_valid)
        """
        parts = self.utterance.split()
        if len(parts) < 3:
            return parts[0] if parts else "", None, None, False

        try:
            amount = int(parts[1].replace(",", ""))
            choice = parts[2].strip()
            return parts[0], amount, choice, True
        except ValueError:
            return parts[0], None, parts[2] if len(parts) > 2 else None, False

    def _parse_stock_query(self, start_index: int = 1) -> str:
        """
        종목명 파싱 (띄어쓰기 포함)
        예: /시세 삼성전자
        """
        parts = self.utterance.split(maxsplit=start_index)
        if len(parts) <= start_index:
            return ""
        return parts[start_index].strip()
