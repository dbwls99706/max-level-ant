"""
예측게임 관련 핸들러
- 복권, 종목추첨, 등락예측, 업다운, 시장예측
"""
from typing import Dict

from services import GameService
from config import GameConfig
from utils import KakaoResponse

from .base_handler import BaseHandlerMixin


class GameHandlerMixin(BaseHandlerMixin):
    """예측게임 관련 핸들러 믹스인"""

    def handle_game_menu(self) -> Dict:
        """예측게임 메뉴"""
        msg = """📈 예측게임

🎫 /복권 - 무료 복권 (1일 5회)
📊 /종목추첨 [금액] - 종목 분석 추첨!
🔮 /시장예측 [금액] [방향] - 시장 흐름 예측!
📉 /등락 [금액] [오름/내림] - 등락 예측!
🔢 /업다운 [금액] [상승/하락] - 숫자 예측!

💡 추천: 종목추첨 대박수익 50배!
⏰ 종목추첨/시장예측/등락/업다운은 장 마감 후 이용 가능"""

        small_bet = GameConfig.DEFAULT_BET
        big_bet = GameConfig.BIG_BET
        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "🎫 복권", "action": "message", "messageText": "/복권"},
                {"label": "📊 5만 추첨", "action": "message", "messageText": f"/종목추첨 {small_bet}"},
                {"label": "📊 50만 추첨", "action": "message", "messageText": f"/종목추첨 {big_bet}"},
                {"label": "🚀 급등 10배!", "action": "message", "messageText": f"/시장예측 {small_bet} 급등"},
                {"label": "📉 등락 50만", "action": "message", "messageText": f"/등락 {big_bet} 오름"}
            ]
        )

    def handle_lottery(self) -> Dict:
        """복권 긁기"""
        result = GameService.play_lottery(self.db, self.kakao_id)

        if not result["success"]:
            bet = GameConfig.DEFAULT_BET
            return KakaoResponse.quick_replies(
                result["message"],
                [
                    {"label": "📊 종목추첨", "action": "message", "messageText": f"/종목추첨 {bet}"},
                    {"label": "📉 등락예측", "action": "message", "messageText": f"/등락 {bet} 오름"},
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
        reward = result["reward"]

        # 남은 횟수에 따른 메시지
        if remaining == 0:
            remaining_msg = "🚫 오늘 복권 모두 소진!"
        elif remaining == 1:
            remaining_msg = "⚡ 마지막 1회 남음!"
        elif remaining == 2:
            remaining_msg = "🔥 2회 남음!"
        else:
            remaining_msg = f"📍 오늘 남은 횟수: {remaining}회"

        reward_text = f"+{reward:,}원" if reward > 0 else "0원"

        msg = f"""🎫 복권 긁기 {effect}

{tier}! {result['message']}

💰 당첨금: {reward_text}

{remaining_msg}
💵 현재 잔고: {result['cash']:,}원"""

        buttons = []
        if remaining > 0:
            buttons.append({"label": "🎫 한번 더!", "action": "message", "messageText": "/복권"})
        buttons.extend([
            {"label": "📊 종목추첨", "action": "message", "messageText": f"/종목추첨 {GameConfig.DEFAULT_BET}"},
            {"label": "🚀 급등주", "action": "message", "messageText": "/급등"},
        ])

        return KakaoResponse.quick_replies(msg, buttons)

    def handle_slot(self) -> Dict:
        """종목추첨"""
        parts = self.utterance.split()

        bet = GameConfig.DEFAULT_BET
        if len(parts) >= 2:
            try:
                bet = int(parts[1].replace(",", ""))
            except ValueError:
                return KakaoResponse.quick_replies(
                    "투자금은 숫자로 입력해주세요.\n예: /종목추첨 50000",
                    [
                        {"label": "📊 1만원", "action": "message", "messageText": "/종목추첨 10000"},
                        {"label": "📊 5만원", "action": "message", "messageText": "/종목추첨 50000"},
                        {"label": "📊 10만원", "action": "message", "messageText": "/종목추첨 100000"}
                    ]
                )

        result = GameService.play_slot(self.db, self.kakao_id, bet)

        if not result["success"]:
            return self._game_failure_response(result["message"])

        slots = result["slots"]
        slot_display = f"[ {slots[0]} | {slots[1]} | {slots[2]} ]"

        # 배율별 메시지
        multiplier = result["multiplier"]
        if result["jackpot"]:
            effect = "🎆🎇🎆 LEGENDARY!!! 🎆🎇🎆"
            encourage = "전설의 수익! 👑"
        elif multiplier >= 10:
            effect = "💎 EPIC WIN! 💎"
            encourage = "대박 수익! 🌟"
        elif multiplier >= 5:
            effect = "🎉 BIG WIN! 🎉"
            encourage = "훌륭한 수익! 🔥"
        elif multiplier > 1:
            effect = "✨ WIN! ✨"
            encourage = "좋은 결과! 🎯"
        elif multiplier > 0:
            effect = "💫 SMALL WIN 💫"
            encourage = "아깝네요, 한번 더!"
        else:
            # 근접 실패 감지 (2개 일치)
            if slots[0] == slots[1] or slots[1] == slots[2] or slots[0] == slots[2]:
                matched_symbol = None
                if slots[0] == slots[1]:
                    matched_symbol = slots[0]
                elif slots[1] == slots[2]:
                    matched_symbol = slots[1]
                else:
                    matched_symbol = slots[0]

                if matched_symbol in ["7️⃣", "💎", "🚀"]:
                    effect = f"🤯🤯 {matched_symbol} 2개!! 대박 직전!!"
                    encourage = f"한 개만 더!! 🔥🔥🔥"
                else:
                    effect = "😱 아깝다!! 2개 일치!"
                    encourage = "거의 다 왔어요! 🔥 다시 한번!"
            else:
                effect = "💨 실패..."
                encourage = "다음엔 될 거예요! 💪"

        if result["profit"] >= 0:
            profit_text = f"📈 +{result['profit']:,}원"
        else:
            profit_text = f"📉 {result['profit']:,}원"

        msg = f"""📊 종목추첨

{slot_display}

{effect}
{encourage}

💰 투자금: {result['bet']:,}원
🎯 배율: x{result['multiplier']}
{profit_text}
💵 잔고: {result['cash']:,}원"""

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "📊 한번 더!", "action": "message", "messageText": f"/종목추첨 {bet}"},
                {"label": "📊 2배 투자", "action": "message", "messageText": f"/종목추첨 {bet * 2}"},
                {"label": "🚀 급등주", "action": "message", "messageText": "/급등"}
            ]
        )

    def handle_coin(self) -> Dict:
        """등락예측"""
        parts = self.utterance.split()

        if len(parts) < 3:
            return KakaoResponse.quick_replies(
                "📉 등락예측\n\n주가가 오를까 내릴까?\n\n사용법: /등락 [금액] [오름/내림]\n예: /등락 100000 오름",
                [
                    {"label": "📈 10만 오름", "action": "message", "messageText": "/등락 100000 오름"},
                    {"label": "📉 10만 내림", "action": "message", "messageText": "/등락 100000 내림"},
                    {"label": "📈 50만 오름", "action": "message", "messageText": "/등락 500000 오름"},
                    {"label": "📉 50만 내림", "action": "message", "messageText": "/등락 500000 내림"}
                ]
            )

        try:
            bet = int(parts[1].replace(",", ""))
        except ValueError:
            return KakaoResponse.quick_replies(
                "투자금은 숫자로 입력해주세요.",
                [
                    {"label": "📈 10만 오름", "action": "message", "messageText": "/등락 100000 오름"},
                    {"label": "📉 10만 내림", "action": "message", "messageText": "/등락 100000 내림"}
                ]
            )

        choice = parts[2].strip()
        result = GameService.play_coin_flip(self.db, self.kakao_id, bet, choice)

        if not result["success"]:
            return self._game_failure_response(result["message"])

        if result["won"]:
            effect = "🎉 적중!"
            profit_text = f"📈 +{result['profit']:,}원"
        else:
            effect = "💨 빗나감"
            profit_text = f"📉 {result['profit']:,}원"

        result_emoji = "📈" if result['result'] == "오름" else "📉"

        msg = f"""📊 등락예측

{result_emoji} 결과: {result['result']}!
🎯 예측: {result['choice']}

{effect}

💰 투자금: {result['bet']:,}원
{profit_text}
💵 잔고: {result['cash']:,}원"""

        opposite = "내림" if result["choice"] == "오름" else "오름"
        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "📊 한번 더!", "action": "message", "messageText": f"/등락 {bet} {result['choice']}"},
                {"label": "📊 2배!", "action": "message", "messageText": f"/등락 {bet * 2} {result['choice']}"},
                {"label": "📊 반대로!", "action": "message", "messageText": f"/등락 {bet} {opposite}"},
                {"label": "🚀 급등주", "action": "message", "messageText": "/급등"}
            ]
        )

    def handle_highlow(self) -> Dict:
        """업다운 예측게임"""
        parts = self.utterance.split()

        if len(parts) < 3:
            return KakaoResponse.quick_replies(
                "🔢 업다운\n\n1~100 중 숫자가 50보다 높을까 낮을까?\n\n사용법: /업다운 [금액] [상승/하락]",
                [
                    {"label": "🔼 10만 상승", "action": "message", "messageText": "/업다운 100000 상승"},
                    {"label": "🔽 10만 하락", "action": "message", "messageText": "/업다운 100000 하락"},
                    {"label": "🔼 50만 상승", "action": "message", "messageText": "/업다운 500000 상승"}
                ]
            )

        try:
            bet = int(parts[1].replace(",", ""))
        except ValueError:
            return KakaoResponse.quick_replies(
                "투자금은 숫자로 입력해주세요.",
                [
                    {"label": "🔼 10만 상승", "action": "message", "messageText": "/업다운 100000 상승"},
                    {"label": "🔽 10만 하락", "action": "message", "messageText": "/업다운 100000 하락"}
                ]
            )

        choice = parts[2].strip()
        result = GameService.play_high_low(self.db, self.kakao_id, bet, choice)

        if not result["success"]:
            return self._game_failure_response(result["message"])

        if result["won"] is None:
            msg = f"""🔢 업다운

🔢 숫자: {result['number']}

😮 무승부! (50)
투자금 반환!

💵 잔고: {result['cash']:,}원"""
        else:
            number = result['number']
            if result["won"]:
                if abs(number - 50) <= 5:
                    effect = "🎉 아슬아슬 적중! 🎉"
                    encourage = "간발의 차이! 짜릿해요! ⚡"
                elif abs(number - 50) >= 40:
                    effect = "🎊 완벽한 적중! 🎊"
                    encourage = "확실한 예측! 👏"
                else:
                    effect = "🎉 적중!"
                    encourage = "좋아요! 계속 가보세요! 🔥"
                profit_text = f"📈 +{result['profit']:,}원"
            else:
                if abs(number - 50) <= 3:
                    effect = "😱 앗!! 거의 맞출 뻔!"
                    encourage = f"50에서 {abs(number-50)}만 차이! 다시 도전! 🔥"
                elif abs(number - 50) <= 10:
                    effect = "😤 아깝다!"
                    encourage = "조금만 더! 💪"
                else:
                    effect = "💨 빗나감"
                    encourage = "다음엔 될 거예요!"
                profit_text = f"📉 {result['profit']:,}원"

            arrow = "🔼" if result["actual"] == "상승" else "🔽"

            msg = f"""🔢 업다운

🔢 숫자: {result['number']} {arrow}
🎯 예측: {result['choice']} / 정답: {result['actual']}

{effect}
{encourage}

💰 투자금: {result['bet']:,}원
{profit_text}
💵 잔고: {result['cash']:,}원"""

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "🔼 상승!", "action": "message", "messageText": f"/업다운 {bet} 상승"},
                {"label": "🔽 하락!", "action": "message", "messageText": f"/업다운 {bet} 하락"},
                {"label": "🔢 2배!", "action": "message", "messageText": f"/업다운 {bet * 2} {result.get('choice', '상승')}"},
                {"label": "🚀 급등주", "action": "message", "messageText": "/급등"}
            ]
        )

    def handle_roulette(self) -> Dict:
        """시장예측 게임"""
        parts = self.utterance.split()

        if len(parts) < 3:
            return KakaoResponse.quick_replies(
                "🔮 시장예측\n\n시장이 어디로 갈까?\n\n📈 상승: 2배 (50%)\n📉 하락: 2.5배 (40%)\n🚀 급등: 10배 (10%)\n\n사용법: /시장예측 [금액] [방향]",
                [
                    {"label": "📈 10만 상승", "action": "message", "messageText": "/시장예측 100000 상승"},
                    {"label": "📉 10만 하락", "action": "message", "messageText": "/시장예측 100000 하락"},
                    {"label": "🚀 10만 급등", "action": "message", "messageText": "/시장예측 100000 급등"}
                ]
            )

        try:
            bet = int(parts[1].replace(",", ""))
        except ValueError:
            return KakaoResponse.quick_replies(
                "투자금은 숫자로 입력해주세요.",
                [
                    {"label": "📈 10만 상승", "action": "message", "messageText": "/시장예측 100000 상승"},
                    {"label": "📉 10만 하락", "action": "message", "messageText": "/시장예측 100000 하락"}
                ]
            )

        choice = parts[2].strip()
        result = GameService.play_roulette(self.db, self.kakao_id, bet, choice)

        if not result["success"]:
            return self._game_failure_response(result["message"])

        if result["won"]:
            effect = "🎉 적중!"
            profit_text = f"📈 +{result['profit']:,}원"
        else:
            effect = "💨 빗나감"
            profit_text = f"📉 {result['profit']:,}원"

        choice_emoji = {"상승": "📈", "하락": "📉", "급등": "🚀"}.get(result["choice"], "")

        msg = f"""🔮 시장예측

{result['emoji']} 결과: {result['result']}!
{choice_emoji} 예측: {result['choice']}

{effect}

💰 투자금: {result['bet']:,}원
{profit_text}
💵 잔고: {result['cash']:,}원"""

        choice_text = result.get("choice", "상승")
        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": f"🔮 {choice_text}!", "action": "message", "messageText": f"/시장예측 {bet} {choice_text}"},
                {"label": "🔮 2배!", "action": "message", "messageText": f"/시장예측 {bet * 2} {choice_text}"},
                {"label": "🚀 급등 10배!", "action": "message", "messageText": f"/시장예측 {bet} 급등"},
                {"label": "🚀 급등주", "action": "message", "messageText": "/급등"}
            ]
        )
