"""
기본 핸들러 믹스인 (개선)
- 공통 기능 제공
- 도파민 요소 강화 (연속 보상, 스트릭, 레벨업)
"""
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from config import is_market_closed, GameConfig
from utils import get_handler_logger, KakaoResponse

logger = get_handler_logger()


class BaseHandlerMixin:
    """핸들러 공통 기능"""

    db: Session
    kakao_id: str
    utterance: str
    nickname: str

    # ===========================================
    # 도파민 요소: 효과음/이펙트
    # ===========================================
    EFFECTS = {
        "jackpot": "🎆🎇🎆🎇🎆",
        "big_win": "✨🎉✨",
        "win": "🎊",
        "small_win": "💫",
        "profit": "📈💰",
        "loss": "📉",
        "streak": ["🔥", "🔥🔥", "🔥🔥🔥", "💎🔥", "⚡🔥⚡"],
        "rank_up": "⬆️🏆",
        "level_up": "🆙✨",
        "milestone": "🏅",
    }

    PROFIT_TIERS = [
        (1_000_000, "🤑 대박!", EFFECTS["jackpot"]),
        (500_000, "💎 잭팟!", EFFECTS["big_win"]),
        (100_000, "🎉 좋아요!", EFFECTS["win"]),
        (10_000, "👍 괜찮네요!", EFFECTS["small_win"]),
        (0, "📈 수익!", ""),
        (-50_000, "😅 아쉽네요", ""),
        (-100_000, "😢 조금 많이...", ""),
        (float('-inf'), "💸 크게 잃었네요", ""),
    ]

    def _get_profit_message(self, profit: int) -> Tuple[str, str]:
        """수익에 따른 도파민 메시지 반환 (메시지, 이펙트)"""
        for threshold, msg, effect in self.PROFIT_TIERS:
            if profit >= threshold:
                return msg, effect
        return "", ""

    def _get_streak_effect(self, streak: int) -> str:
        """연속 횟수에 따른 이펙트"""
        effects = self.EFFECTS["streak"]
        if streak <= 0:
            return ""
        if streak <= len(effects):
            return effects[streak - 1]
        return effects[-1] + f" x{streak}"

    # ===========================================
    # Quick Reply 버튼 헬퍼
    # ===========================================

    def _get_game_buttons(self) -> list:
        """장 마감 시간에만 게임 버튼 반환"""
        if is_market_closed():
            return [
                {"label": "🎰 게임", "action": "message", "messageText": "/게임"}
            ]
        return []

    def _get_quick_trade_buttons(self, stock_name: str = None) -> List[Dict]:
        """빠른 거래 버튼"""
        buttons = []
        if stock_name:
            buttons.extend([
                {"label": f"📈 {stock_name} 매수", "action": "message", "messageText": f"/매수 {stock_name} 10"},
                {"label": f"📉 {stock_name} 매도", "action": "message", "messageText": f"/매도 {stock_name} 10"},
            ])
        buttons.extend([
            {"label": "🚀 급등주", "action": "message", "messageText": "/급등"},
            {"label": "💼 포폴", "action": "message", "messageText": "/포트폴리오"},
        ])
        return buttons

    def _get_continue_game_buttons(self, game_type: str, bet: int, choice: str = None) -> List[Dict]:
        """게임 계속하기 버튼 (도파민 유도)"""
        buttons = []

        if game_type == "lottery":
            buttons.append({"label": "🎫 한번 더!", "action": "message", "messageText": "/복권"})
        elif game_type == "slot":
            buttons.extend([
                {"label": "🎰 한번 더!", "action": "message", "messageText": f"/슬롯머신 {bet}"},
                {"label": "🎰 2배 배팅!", "action": "message", "messageText": f"/슬롯머신 {bet * 2}"},
            ])
        elif game_type == "coin":
            opposite = "뒤" if choice == "앞" else "앞"
            buttons.extend([
                {"label": "🪙 한번 더!", "action": "message", "messageText": f"/동전 {bet} {choice}"},
                {"label": f"🪙 {opposite}으로!", "action": "message", "messageText": f"/동전 {bet} {opposite}"},
            ])
        elif game_type == "highlow":
            opposite = "낮" if choice == "높" else "높"
            buttons.extend([
                {"label": "🎲 한번 더!", "action": "message", "messageText": f"/하이로우 {bet} {choice}"},
                {"label": f"🎲 {opposite}으로!", "action": "message", "messageText": f"/하이로우 {bet} {opposite}"},
            ])
        elif game_type == "roulette":
            buttons.extend([
                {"label": "🔴 빨강!", "action": "message", "messageText": f"/룰렛 {bet} 빨강"},
                {"label": "⚫ 검정!", "action": "message", "messageText": f"/룰렛 {bet} 검정"},
                {"label": "🟢 초록!", "action": "message", "messageText": f"/룰렛 {bet} 초록"},
            ])

        # 다른 게임 추천
        buttons.append({"label": "🎰 다른 게임", "action": "message", "messageText": "/게임"})
        return buttons

    def _get_navigation_buttons(self) -> List[Dict]:
        """기본 내비게이션 버튼"""
        buttons = [
            {"label": "🚀 급등주", "action": "message", "messageText": "/급등"},
            {"label": "💼 포폴", "action": "message", "messageText": "/포트폴리오"},
        ]
        buttons.extend(self._get_game_buttons())
        return buttons

    def _get_after_trade_buttons(self, stock_name: str, action: str = "buy") -> List[Dict]:
        """거래 후 추천 버튼 (도파민 유지)"""
        buttons = []

        if action == "buy":
            buttons.extend([
                {"label": f"📈 {stock_name} 더 매수", "action": "message", "messageText": f"/전량매수 {stock_name}"},
                {"label": f"📊 {stock_name} 시세", "action": "message", "messageText": f"/시세 {stock_name}"},
            ])
        else:
            buttons.extend([
                {"label": f"📊 {stock_name} 시세", "action": "message", "messageText": f"/시세 {stock_name}"},
            ])

        buttons.extend([
            {"label": "💼 포폴 확인", "action": "message", "messageText": "/포트폴리오"},
            {"label": "🚀 다른 급등주", "action": "message", "messageText": "/급등"},
        ])
        buttons.extend(self._get_game_buttons())
        return buttons

    def _get_ranking_climb_buttons(self) -> List[Dict]:
        """랭킹 상승 유도 버튼"""
        return [
            {"label": "🚀 급등주 투자", "action": "message", "messageText": "/급등"},
            {"label": "📉 저점매수", "action": "message", "messageText": "/급락"},
            {"label": "🎰 게임으로 도전", "action": "message", "messageText": "/게임"},
            {"label": "💼 포폴", "action": "message", "messageText": "/포트폴리오"},
        ]

    # ===========================================
    # 파싱 헬퍼
    # ===========================================

    def _parse_parts(self, min_parts: int = 2) -> Tuple[List[str], bool]:
        """
        명령어 파싱
        Returns: (parts, is_valid)
        """
        parts = self.utterance.split()
        if len(parts) < min_parts:
            return parts, False
        return parts, True

    def _parse_with_amount(self) -> Tuple[str, Optional[int], bool]:
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

    def _parse_with_choice(self) -> Tuple[str, Optional[int], Optional[str], bool]:
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

    # ===========================================
    # 메시지 포맷팅 헬퍼
    # ===========================================

    def _format_profit(self, profit: int) -> str:
        """수익 포맷팅"""
        if profit > 0:
            return f"📈 +{profit:,}원"
        elif profit < 0:
            return f"📉 {profit:,}원"
        return "➖ ±0원"

    def _format_rate(self, rate: float) -> str:
        """수익률 포맷팅"""
        if rate > 0:
            return f"▲{rate:+.2f}%"
        elif rate < 0:
            return f"▼{rate:.2f}%"
        return "0.00%"

    def _get_sell_celebration(self, profit_rate: float, profit: int = 0) -> str:
        """수익률 기반 축하 메시지 (매도 시 사용) - 도파민 극대화"""
        if profit_rate >= 100:
            return "🎆🎇🚀💰🎆🎇\n\n🏆 전설의 수익! +100%! 👑\n당신은 진정한 주식왕!"
        elif profit_rate >= 50:
            return "🎉🔥✨\n\n💎 대박! +50% 수익!\n투자의 신이 되셨습니다!"
        elif profit_rate >= 30:
            return "🎊🌟\n\n🚀 멋져요! +30% 수익!\n프로 트레이더 인정!"
        elif profit_rate >= 20:
            return "🎊 훌륭해요! +20% 이상 수익! 🌟"
        elif profit_rate >= 10:
            return "📈 좋은 거래! 꾸준히 가세요! 💪"
        elif profit_rate >= 5:
            return "✨ 수익 실현 성공! 잘하셨어요!"
        elif profit_rate >= 0:
            return "✅ 수익 마감! 본전 이상은 성공!"
        elif profit_rate >= -5:
            return "💫 작은 손실, 다음이 기회예요!"
        elif profit_rate >= -10:
            return "😅 아쉽지만 경험이 됐어요!"
        elif profit_rate >= -20:
            return "😤 회복 가능! 다시 도전하세요!"
        elif profit_rate >= -30:
            return "😢 조금 많이... 분할매매 추천드려요"
        else:
            return "💪 큰 손실이지만 포기하지 마세요!\n🎯 급등주에서 재기 가능!"

    def _add_celebration(self, msg: str, profit: int) -> str:
        """큰 수익에 축하 이펙트 추가"""
        celebration_msg, effect = self._get_profit_message(profit)
        if effect:
            return f"{effect}\n\n{msg}"
        return msg

    # ===========================================
    # 공통 에러 응답 (중복 제거)
    # ===========================================

    def _market_closed_response(self) -> Dict:
        """장 마감 시 공통 응답 (게임 유도)"""
        return KakaoResponse.quick_replies(
            "📢 현재 장이 열려있지 않아요!\n\n"
            "🎮 장 마감 시간에는 미니게임을 즐겨보세요!",
            [
                {"label": "🎫 복권", "action": "message", "messageText": "/복권"},
                {"label": "🎰 슬롯머신", "action": "message", "messageText": f"/슬롯머신 {GameConfig.DEFAULT_BET}"},
                {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
            ]
        )

    def _market_closed_with_message(self, message: str) -> Dict:
        """장 마감 시 커스텀 메시지 응답"""
        return KakaoResponse.quick_replies(
            message,
            [
                {"label": "🎫 복권", "action": "message", "messageText": "/복권"},
                {"label": "🎰 슬롯머신", "action": "message", "messageText": f"/슬롯머신 {GameConfig.DEFAULT_BET}"},
                {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
            ]
        )

    def _check_market_closed_error(self, result: Dict) -> tuple:
        """
        서비스 결과에서 MARKET_CLOSED 에러 확인
        Returns: (is_market_closed, response or None)
        """
        if not result.get("success") and result.get("error_code") == "MARKET_CLOSED":
            return True, self._market_closed_with_message(result.get("message", "장이 마감되었습니다."))
        return False, None
