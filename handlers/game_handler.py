"""
미니게임 관련 핸들러
- 복권, 슬롯머신, 동전던지기, 하이로우, 룰렛
"""
from typing import Dict

from services import GameService
from utils import KakaoResponse

from .base_handler import BaseHandlerMixin


class GameHandlerMixin(BaseHandlerMixin):
    """미니게임 관련 핸들러 믹스인"""

    def handle_game_menu(self) -> Dict:
        """게임 메뉴"""
        msg = """🎰 미니게임

🎫 /복권 - 1만원 복권 (1일 5회)
🎰 /슬롯머신 [금액] - 슬롯머신
🎡 /룰렛 [금액] [색상] - 색상 맞추기
🪙 /동전 [금액] [앞/뒤] - 동전던지기
🎲 /하이로우 [금액] [높/낮] - 숫자게임

⏰ 슬롯/룰렛/동전/하이로우는 장 마감 후 이용 가능"""

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "🎫 복권", "action": "message", "messageText": "/복권"},
                {"label": "🎰 슬롯머신", "action": "message", "messageText": "/슬롯머신 50000"},
                {"label": "🎡 룰렛", "action": "message", "messageText": "/룰렛 50000 빨강"},
                {"label": "🪙 동전던지기", "action": "message", "messageText": "/동전 50000 앞"},
                {"label": "🎲 하이로우", "action": "message", "messageText": "/하이로우 50000 높"}
            ]
        )

    def handle_lottery(self) -> Dict:
        """복권 긁기"""
        result = GameService.play_lottery(self.db, self.kakao_id)

        if not result["success"]:
            return KakaoResponse.quick_replies(
                result["message"],
                [
                    {"label": "🎰 슬롯머신", "action": "message", "messageText": "/슬롯머신 50000"},
                    {"label": "🪙 동전던지기", "action": "message", "messageText": "/동전 50000 앞"},
                    {"label": "🚀 급등주", "action": "message", "messageText": "/급등"}
                ]
            )

        tier = result["tier"]
        if "대박" in tier:
            effect = "🎆🎇🎆🎇🎆"
        elif "1등" in tier:
            effect = "✨✨✨"
        elif "2등" in tier:
            effect = "🎉🎉"
        elif "3등" in tier:
            effect = "🎊"
        else:
            effect = ""

        remaining = result.get("remaining", 0)
        profit = result.get("profit", 0)
        profit_emoji = "📈" if profit > 0 else "📉" if profit < 0 else "➖"
        profit_text = f"+{profit:,}" if profit > 0 else f"{profit:,}"

        msg = f"""🎫 복권 긁기 {effect}

{tier}! {result['message']}

🎟️ 복권 가격: -{result['cost']:,}원
💰 당첨금: +{result['reward']:,}원
{profit_emoji} 순이익: {profit_text}원

📍 오늘 남은 횟수: {remaining}회
💵 현재 잔고: {result['cash']:,}원"""

        buttons = []
        if remaining > 0:
            buttons.append({"label": "🎫 한번 더!", "action": "message", "messageText": "/복권"})
        buttons.extend([
            {"label": "🎰 슬롯머신", "action": "message", "messageText": "/슬롯머신 50000"},
            {"label": "🚀 급등주", "action": "message", "messageText": "/급등"},
        ])

        return KakaoResponse.quick_replies(msg, buttons)

    def handle_slot(self) -> Dict:
        """슬롯머신"""
        parts = self.utterance.split()

        bet = 50_000
        if len(parts) >= 2:
            try:
                bet = int(parts[1].replace(",", ""))
            except ValueError:
                return KakaoResponse.quick_replies(
                    "배팅금은 숫자로 입력해주세요.\n예: /슬롯머신 50000",
                    [
                        {"label": "🎰 1만원", "action": "message", "messageText": "/슬롯머신 10000"},
                        {"label": "🎰 5만원", "action": "message", "messageText": "/슬롯머신 50000"},
                        {"label": "🎰 10만원", "action": "message", "messageText": "/슬롯머신 100000"}
                    ]
                )

        result = GameService.play_slot(self.db, self.kakao_id, bet)

        if not result["success"]:
            return KakaoResponse.quick_replies(
                result["message"],
                [
                    {"label": "📅 출석체크", "action": "message", "messageText": "/출석"},
                    {"label": "🎫 복권", "action": "message", "messageText": "/복권"},
                    {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
                ]
            )

        slots = result["slots"]
        slot_display = f"[ {slots[0]} | {slots[1]} | {slots[2]} ]"

        if result["jackpot"]:
            effect = "🎆 JACKPOT!!! 🎆"
        elif result["multiplier"] >= 5:
            effect = "🎉 BIG WIN! 🎉"
        elif result["multiplier"] > 0:
            effect = "✨ WIN! ✨"
        else:
            effect = "💨 실패..."

        if result["profit"] >= 0:
            profit_text = f"📈 +{result['profit']:,}원"
        else:
            profit_text = f"📉 {result['profit']:,}원"

        msg = f"""🎰 슬롯머신

{slot_display}

{effect}

💰 배팅: {result['bet']:,}원
🎯 배율: x{result['multiplier']}
{profit_text}
💵 잔고: {result['cash']:,}원"""

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "🎰 한번 더!", "action": "message", "messageText": f"/슬롯머신 {bet}"},
                {"label": "🎰 2배 배팅", "action": "message", "messageText": f"/슬롯머신 {bet * 2}"},
                {"label": "🚀 급등주", "action": "message", "messageText": "/급등"}
            ]
        )

    def handle_coin(self) -> Dict:
        """동전 던지기"""
        parts = self.utterance.split()

        if len(parts) < 3:
            return KakaoResponse.quick_replies(
                "🪙 동전 던지기\n\n사용법: /동전 [금액] [앞/뒤]\n예: /동전 100000 앞",
                [
                    {"label": "🪙 10만 앞", "action": "message", "messageText": "/동전 100000 앞"},
                    {"label": "🪙 10만 뒤", "action": "message", "messageText": "/동전 100000 뒤"},
                    {"label": "🪙 50만 앞", "action": "message", "messageText": "/동전 500000 앞"},
                    {"label": "🪙 50만 뒤", "action": "message", "messageText": "/동전 500000 뒤"}
                ]
            )

        try:
            bet = int(parts[1].replace(",", ""))
        except ValueError:
            return KakaoResponse.quick_replies(
                "배팅금은 숫자로 입력해주세요.",
                [
                    {"label": "🪙 10만 앞", "action": "message", "messageText": "/동전 100000 앞"},
                    {"label": "🪙 10만 뒤", "action": "message", "messageText": "/동전 100000 뒤"}
                ]
            )

        choice = parts[2].strip()
        result = GameService.play_coin_flip(self.db, self.kakao_id, bet, choice)

        if not result["success"]:
            return KakaoResponse.quick_replies(
                result["message"],
                [
                    {"label": "📅 출석체크", "action": "message", "messageText": "/출석"},
                    {"label": "🎫 복권", "action": "message", "messageText": "/복권"},
                    {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
                ]
            )

        if result["won"]:
            effect = "🎉 WIN!"
            profit_text = f"📈 +{result['profit']:,}원"
        else:
            effect = "💨 LOSE"
            profit_text = f"📉 {result['profit']:,}원"

        msg = f"""🪙 동전 던지기

{result['emoji']} 결과: {result['result']}!
🎯 선택: {result['choice']}

{effect}

💰 배팅: {result['bet']:,}원
{profit_text}
💵 잔고: {result['cash']:,}원"""

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "🪙 한번 더!", "action": "message", "messageText": f"/동전 {bet} {choice}"},
                {"label": "🪙 반대로!", "action": "message", "messageText": f"/동전 {bet} {'뒤' if choice == '앞' else '앞'}"},
                {"label": "🚀 급등주", "action": "message", "messageText": "/급등"}
            ]
        )

    def handle_highlow(self) -> Dict:
        """하이로우 게임"""
        parts = self.utterance.split()

        if len(parts) < 3:
            return KakaoResponse.quick_replies(
                "🎲 하이로우\n\n1~100 중 숫자가 50보다 높을까 낮을까?\n\n사용법: /하이로우 [금액] [높/낮]",
                [
                    {"label": "🔼 10만 높", "action": "message", "messageText": "/하이로우 100000 높"},
                    {"label": "🔽 10만 낮", "action": "message", "messageText": "/하이로우 100000 낮"},
                    {"label": "🔼 50만 높", "action": "message", "messageText": "/하이로우 500000 높"}
                ]
            )

        try:
            bet = int(parts[1].replace(",", ""))
        except ValueError:
            return KakaoResponse.quick_replies(
                "배팅금은 숫자로 입력해주세요.",
                [
                    {"label": "🔼 10만 높", "action": "message", "messageText": "/하이로우 100000 높"},
                    {"label": "🔽 10만 낮", "action": "message", "messageText": "/하이로우 100000 낮"}
                ]
            )

        choice = parts[2].strip()
        result = GameService.play_high_low(self.db, self.kakao_id, bet, choice)

        if not result["success"]:
            return KakaoResponse.quick_replies(
                result["message"],
                [
                    {"label": "📅 출석체크", "action": "message", "messageText": "/출석"},
                    {"label": "🎫 복권", "action": "message", "messageText": "/복권"},
                    {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
                ]
            )

        if result["won"] is None:
            msg = f"""🎲 하이로우

🔢 숫자: {result['number']}

😮 무승부! (50)
배팅금 반환!

💵 잔고: {result['cash']:,}원"""
        else:
            if result["won"]:
                effect = "🎉 WIN!"
                profit_text = f"📈 +{result['profit']:,}원"
            else:
                effect = "💨 LOSE"
                profit_text = f"📉 {result['profit']:,}원"

            arrow = "🔼" if result["actual"] == "높" else "🔽"

            msg = f"""🎲 하이로우

🔢 숫자: {result['number']} {arrow}
🎯 선택: {result['choice']} / 정답: {result['actual']}

{effect}

💰 배팅: {result['bet']:,}원
{profit_text}
💵 잔고: {result['cash']:,}원"""

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "🔼 높!", "action": "message", "messageText": f"/하이로우 {bet} 높"},
                {"label": "🔽 낮!", "action": "message", "messageText": f"/하이로우 {bet} 낮"},
                {"label": "🚀 급등주", "action": "message", "messageText": "/급등"}
            ]
        )

    def handle_roulette(self) -> Dict:
        """룰렛 게임"""
        parts = self.utterance.split()

        if len(parts) < 3:
            return KakaoResponse.quick_replies(
                "🎡 룰렛\n\n빨강/검정/초록 중 하나를 선택!\n\n🔴 빨강: 2배 (45%)\n⚫ 검정: 2배 (45%)\n🟢 초록: 9배 (10%)\n\n사용법: /룰렛 [금액] [색상]",
                [
                    {"label": "🔴 10만 빨강", "action": "message", "messageText": "/룰렛 100000 빨강"},
                    {"label": "⚫ 10만 검정", "action": "message", "messageText": "/룰렛 100000 검정"},
                    {"label": "🟢 10만 초록", "action": "message", "messageText": "/룰렛 100000 초록"}
                ]
            )

        try:
            bet = int(parts[1].replace(",", ""))
        except ValueError:
            return KakaoResponse.quick_replies(
                "배팅금은 숫자로 입력해주세요.",
                [
                    {"label": "🔴 10만 빨강", "action": "message", "messageText": "/룰렛 100000 빨강"},
                    {"label": "⚫ 10만 검정", "action": "message", "messageText": "/룰렛 100000 검정"}
                ]
            )

        choice = parts[2].strip()
        result = GameService.play_roulette(self.db, self.kakao_id, bet, choice)

        if not result["success"]:
            return KakaoResponse.quick_replies(
                result["message"],
                [
                    {"label": "📅 출석체크", "action": "message", "messageText": "/출석"},
                    {"label": "🎫 복권", "action": "message", "messageText": "/복권"},
                    {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
                ]
            )

        if result["won"]:
            effect = "🎉 WIN!"
            profit_text = f"📈 +{result['profit']:,}원"
        else:
            effect = "💨 LOSE"
            profit_text = f"📉 {result['profit']:,}원"

        choice_emoji = {"빨강": "🔴", "검정": "⚫", "초록": "🟢"}.get(result["choice"], "")

        msg = f"""🎡 룰렛

{result['emoji']} 결과: {result['result']}!
{choice_emoji} 선택: {result['choice']}

{effect}

💰 배팅: {result['bet']:,}원
{profit_text}
💵 잔고: {result['cash']:,}원"""

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "🔴 빨강!", "action": "message", "messageText": f"/룰렛 {bet} 빨강"},
                {"label": "⚫ 검정!", "action": "message", "messageText": f"/룰렛 {bet} 검정"},
                {"label": "🟢 초록!", "action": "message", "messageText": f"/룰렛 {bet} 초록"}
            ]
        )
