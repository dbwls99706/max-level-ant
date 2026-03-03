"""
예측게임 관련 핸들러
- 복권, 시장예측(역사 퀴즈), 업다운(멀티라운드), 각성(투자 감각 각성)
"""
from typing import Dict

from services import GameService
from services.enhance_service import EnhanceService
from config import GameConfig, EnhanceConfig
from utils import KakaoResponse

from .base_handler import BaseHandlerMixin


class GameHandlerMixin(BaseHandlerMixin):
    """예측게임 관련 핸들러 믹스인"""

    def handle_game_menu(self) -> Dict:
        """예측게임 메뉴"""
        msg = """📈 예측게임

🎫 /복권 - 무료 복권 (1일 5회)
🔮 /시장예측 [금액] - 주식 역사 퀴즈!
🔢 /업다운 [금액] - 숫자 예측 게임!
🧬 /각성 - 투자 감각 각성!

💡 시장예측: 실제 주식 역사로 상승/하락 맞추기!
💡 업다운: 연속으로 맞출수록 배율 UP!
💡 각성: 투자 능력 UP → 출석/복권 보상 UP!
⏰ 시장예측/업다운은 장 마감 후 이용 가능"""

        small_bet = GameConfig.DEFAULT_BET
        big_bet = GameConfig.BIG_BET
        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "🎫 복권", "action": "message", "messageText": "/복권"},
                {"label": "🧬 각성", "action": "message", "messageText": "/각성"},
                {"label": "🔮 5만 퀴즈", "action": "message", "messageText": f"/시장예측 {small_bet}"},
                {"label": "🔮 50만 퀴즈", "action": "message", "messageText": f"/시장예측 {big_bet}"},
                {"label": "🔢 5만 업다운", "action": "message", "messageText": f"/업다운 {small_bet}"},
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
                    {"label": "🔮 시장예측", "action": "message", "messageText": f"/시장예측 {bet}"},
                    {"label": "🔢 업다운", "action": "message", "messageText": f"/업다운 {bet}"},
                    {"label": "🚀 급등주", "action": "message", "messageText": "/급등"}
                ]
            )

        tier = result["tier"]
        reward = result["reward"]
        remaining = result.get("remaining", 0)
        is_big_win = "1등" in tier or "2등" in tier

        # 등급별 연출
        if "1등" in tier:
            effect = "🎆🎇🎆🎇🎆"
            reveal = "스르르... 번쩍!"
        elif "2등" in tier:
            effect = "✨🎉✨"
            reveal = "스르르... 오!"
        elif "3등" in tier:
            effect = "🎊"
            reveal = "스르르..."
        elif "4등" in tier or "5등" in tier:
            effect = ""
            reveal = "스르르..."
        else:
            effect = ""
            reveal = "스르르..."

        # 남은 횟수 — 긴급성 연출
        if remaining == 0:
            remaining_msg = "🚫 오늘 복권 모두 소진!"
        elif remaining == 1:
            remaining_msg = "⚡ 마지막 1회 남음!"
        elif remaining == 2:
            remaining_msg = "🔥 2회 남음!"
        else:
            remaining_msg = f"📍 오늘 남은 횟수: {remaining}회"

        reward_text = f"+{reward:,}원" if reward > 0 else "0원"

        # 각성 보너스 표시
        enhance_bonus = result.get("enhance_bonus", 0)
        enhance_line = ""
        if enhance_bonus > 0:
            enhance_line = f"\n🧬 각성 보너스: +{enhance_bonus:,}원 (Lv.{result.get('enhance_level', 0)})"

        # Near-miss 아까움 연출 (꽝일 때)
        near_miss_line = ""
        near_miss_tier = result.get("near_miss_tier")
        if near_miss_tier and reward == 0:
            near_miss_reward = result.get("near_miss_reward", 0)
            near_miss_line = f"\n\n😱 아깝다! {near_miss_tier} ({near_miss_reward:,}원)까지 한 끗 차이였어요..."

        msg = f"""🎫 복권 긁기... {reveal}

{effect}
{tier}! {result['message']}

💰 당첨금: {reward_text}{enhance_line}{near_miss_line}

{remaining_msg}
💵 현재 잔고: {result['cash']:,}원"""

        buttons = []
        if remaining > 0:
            buttons.append({"label": "🎫 한번 더!", "action": "message", "messageText": "/복권"})
        # 대박 시 랭킹 버튼 추가
        if is_big_win:
            buttons.append({"label": "🏆 랭킹 확인", "action": "message", "messageText": "/랭킹"})
        buttons.extend([
            {"label": "🔮 시장예측", "action": "message", "messageText": f"/시장예측 {GameConfig.DEFAULT_BET}"},
            {"label": "🧬 각성", "action": "message", "messageText": "/각성"},
        ])

        return KakaoResponse.quick_replies(msg, buttons)

    # ==========================================
    # 시장예측 (역사 퀴즈)
    # ==========================================

    def handle_stock_quiz(self) -> Dict:
        """시장예측 — 역사 퀴즈"""
        parts = self.utterance.split()

        if len(parts) < 2:
            return KakaoResponse.quick_replies(
                "🔮 시장예측 — 주식 역사 퀴즈!\n\n"
                "실제 한국 주식의 역사 데이터로\n"
                "해당 기간에 주가가 올랐는지 내렸는지 맞춰보세요!\n\n"
                "맞추면 x2 배율!\n\n"
                "사용법: /시장예측 [금액]\n"
                "예: /시장예측 100000",
                [
                    {"label": "🔮 5만원", "action": "message", "messageText": "/시장예측 50000"},
                    {"label": "🔮 10만원", "action": "message", "messageText": "/시장예측 100000"},
                    {"label": "🔮 50만원", "action": "message", "messageText": "/시장예측 500000"},
                ]
            )

        try:
            bet = int(parts[1].replace(",", ""))
        except ValueError:
            return KakaoResponse.quick_replies(
                "투자금은 숫자로 입력해주세요.\n예: /시장예측 100000",
                [
                    {"label": "🔮 5만원", "action": "message", "messageText": "/시장예측 50000"},
                    {"label": "🔮 10만원", "action": "message", "messageText": "/시장예측 100000"},
                ]
            )

        # 선택지가 없으면 퀴즈 출제 (상승/하락 선택 유도)
        if len(parts) < 3:
            # 먼저 퀴즈 문제를 보여주고 유저가 선택하게 함
            import random
            from config import GameProbability
            quiz = random.choice(GameProbability.HISTORICAL_STOCK_DATA)

            return KakaoResponse.quick_replies(
                f"🔮 시장예측 — 역사 퀴즈!\n\n"
                f"📊 종목: {quiz['stock_name']}\n"
                f"📅 기간: {quiz['period']}\n\n"
                f"💰 투자금: {bet:,}원\n"
                f"🎯 맞추면: {bet * 2:,}원 획득!\n\n"
                f"이 기간 동안 주가가 올랐을까, 내렸을까?",
                [
                    {"label": "📈 상승!", "action": "message",
                     "messageText": f"/시장예측 {bet} 상승 {quiz['stock_name']}|{quiz['period']}"},
                    {"label": "📉 하락!", "action": "message",
                     "messageText": f"/시장예측 {bet} 하락 {quiz['stock_name']}|{quiz['period']}"},
                ]
            )

        # 선택지가 있으면 정답 확인
        choice = parts[2].strip()

        # 특정 퀴즈 지정 여부 확인 (버튼에서 온 경우)
        specific_quiz = None
        if len(parts) >= 4:
            quiz_key = " ".join(parts[3:])
            if "|" in quiz_key:
                stock_name, period = quiz_key.split("|", 1)
                from config import GameProbability
                for q in GameProbability.HISTORICAL_STOCK_DATA:
                    if q["stock_name"] == stock_name and q["period"] == period:
                        specific_quiz = q
                        break

        if specific_quiz:
            # 특정 퀴즈로 직접 판정
            result = self._play_quiz_with_specific(bet, choice, specific_quiz)
        else:
            # 랜덤 퀴즈
            result = GameService.play_stock_quiz(self.db, self.kakao_id, bet, choice)

        if not result["success"]:
            return self._game_failure_response(result["message"])

        quiz = result["quiz"]

        if result["won"]:
            effect = "🎉 정답!"
            profit_text = f"📈 +{result['profit']:,}원"
            encourage = "실제 역사를 꿰뚫어 보셨네요! 👏"
        else:
            effect = "💨 오답!"
            profit_text = f"📉 {result['profit']:,}원"
            encourage = "이 사건을 기억해두세요! 다음에 써먹을 수 있어요 💪"

        answer_emoji = "📈" if quiz["answer"] == "상승" else "📉"

        # 투자 교훈 생성 — 역사 데이터 기반 맥락 제공
        lesson = self._generate_quiz_lesson(quiz)

        msg = f"""🔮 시장예측 — 역사 퀴즈

📊 {quiz['stock_name']}
📅 {quiz['period']}

{answer_emoji} 정답: {quiz['answer']}!
🎯 내 선택: {result['choice']}

{effect}
{encourage}

📰 당시 상황
{quiz['description']}

{lesson}

💰 투자금: {result['bet']:,}원
{profit_text}
💵 잔고: {result['cash']:,}원"""

        buttons = [
            {"label": "🔮 한번 더!", "action": "message", "messageText": f"/시장예측 {bet}"},
            {"label": "🔮 2배!", "action": "message", "messageText": f"/시장예측 {bet * 2}"},
        ]
        # 큰 판돈(50만원 이상) 정답 시 랭킹 버튼
        if result["won"] and result["bet"] >= 500_000:
            buttons.append({"label": "🏆 랭킹 확인", "action": "message", "messageText": "/랭킹"})
        else:
            buttons.append({"label": "🔢 업다운", "action": "message", "messageText": f"/업다운 {bet}"})
        buttons.append({"label": "🚀 급등주", "action": "message", "messageText": "/급등"})

        return KakaoResponse.quick_replies(msg, buttons)

    def _play_quiz_with_specific(self, bet: int, choice: str, quiz: dict) -> Dict:
        """특정 퀴즈로 직접 판정 (버튼에서 퀴즈가 지정된 경우)"""
        from services.common import (
            get_user_with_error_for_update, validate_bet,
            check_market_closed_for_game, error_response,
            safe_add, safe_subtract, safe_multiply
        )
        from config import GameProbability, ErrorCode
        from utils import log_game

        can_play, market_error = check_market_closed_for_game("🔮")
        if not can_play:
            return market_error

        user, error = get_user_with_error_for_update(self.db, self.kakao_id)
        if error:
            return error

        is_valid, bet_error = validate_bet(bet, user.cash)
        if not is_valid:
            return error_response(ErrorCode.INVALID_BET, bet_error)

        choice_normalized = choice.strip()
        if choice_normalized not in ["상승", "하락"]:
            if choice_normalized in ["상", "up", "오름"]:
                choice_normalized = "상승"
            elif choice_normalized in ["하", "down", "내림"]:
                choice_normalized = "하락"
            else:
                return error_response(ErrorCode.INVALID_CHOICE, "상승 또는 하락 중 선택해주세요.")

        user.cash = safe_subtract(user.cash, bet)
        won = (choice_normalized == quiz["answer"])

        if won:
            multiplier = GameProbability.STOCK_QUIZ_MULTIPLIER
            winnings = safe_multiply(bet, multiplier)
        else:
            multiplier = 0
            winnings = 0

        user.cash = safe_add(user.cash, winnings)

        from sqlalchemy.exc import SQLAlchemyError
        try:
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            return error_response(ErrorCode.DB_ERROR, "데이터베이스 오류가 발생했습니다.")

        log_game(
            kakao_id=self.kakao_id, game_type="STOCK_QUIZ",
            bet=bet, result=f"{quiz['answer']}({'WIN' if won else 'LOSE'})",
            winnings=winnings, profit=winnings - bet, cash_after=user.cash,
            extra=f"stock={quiz['stock_name']} period={quiz['period']} choice={choice_normalized}"
        )

        return {
            "success": True,
            "quiz": quiz,
            "choice": choice_normalized,
            "answer": quiz["answer"],
            "won": won,
            "bet": bet,
            "multiplier": multiplier,
            "winnings": winnings,
            "profit": winnings - bet,
            "cash": user.cash
        }

    # ==========================================
    # 업다운 (멀티라운드)
    # ==========================================

    def handle_updown(self) -> Dict:
        """업다운 게임 — 시작 또는 라운드 진행"""
        parts = self.utterance.split()

        # /업다운 만 입력한 경우
        if len(parts) == 1:
            # 진행중인 게임이 있는지 확인
            status = GameService.get_updown_status(self.db, self.kakao_id)
            if status.get("active"):
                return self._updown_status_response(status)

            return KakaoResponse.quick_replies(
                "🔢 업다운 — 숫자 예측 게임!\n\n"
                "1~100 숫자가 나오면\n"
                "다음 숫자가 높을지 낮을지 예측!\n\n"
                "✅ 맞추면: 배율 누적, 계속 도전!\n"
                "❌ 틀리면: 투자금 전액 손실!\n"
                "💰 정산: 원할 때 수익 확정!\n\n"
                "사용법: /업다운 [금액]",
                [
                    {"label": "🔢 5만원", "action": "message", "messageText": "/업다운 50000"},
                    {"label": "🔢 10만원", "action": "message", "messageText": "/업다운 100000"},
                    {"label": "🔢 50만원", "action": "message", "messageText": "/업다운 500000"},
                ]
            )

        # /업다운 [상승/하락] — 진행중인 게임의 라운드 진행
        if len(parts) == 2 and not parts[1].replace(",", "").isdigit():
            choice = parts[1]
            return self._handle_updown_round(choice)

        # /업다운 [금액] — 새 게임 시작
        try:
            bet = int(parts[1].replace(",", ""))
        except ValueError:
            return KakaoResponse.quick_replies(
                "투자금은 숫자로 입력해주세요.\n예: /업다운 50000",
                [
                    {"label": "🔢 5만원", "action": "message", "messageText": "/업다운 50000"},
                    {"label": "🔢 10만원", "action": "message", "messageText": "/업다운 100000"},
                ]
            )

        # /업다운 [금액] [상승/하락] — 새 게임은 금액만, 라운드는 별도
        if len(parts) >= 3:
            # 혹시 진행중인 게임이 있으면 라운드로 처리
            choice = parts[2]
            status = GameService.get_updown_status(self.db, self.kakao_id)
            if status.get("active"):
                return self._handle_updown_round(choice)

        result = GameService.start_updown(self.db, self.kakao_id, bet)

        if not result["success"]:
            if result.get("active_game"):
                return self._updown_active_game_response(result)
            return self._game_failure_response(result["message"])

        number = result["number"]
        up_mult = result["up_multiplier"]
        down_mult = result["down_multiplier"]

        msg = f"""🔢 업다운 시작!

🎲 첫 번째 숫자: {number}

다음 숫자가 {number}보다 높을까? 낮을까?

📈 상승 선택 시 배율: x{up_mult}
📉 하락 선택 시 배율: x{down_mult}

💰 투자금: {result['bet']:,}원
💵 잔고: {result['cash']:,}원"""

        buttons = []
        if result["can_up"]:
            buttons.append({"label": f"📈 상승 (x{up_mult})", "action": "message", "messageText": "/업다운 상승"})
        if result["can_down"]:
            buttons.append({"label": f"📉 하락 (x{down_mult})", "action": "message", "messageText": "/업다운 하락"})

        return KakaoResponse.quick_replies(msg, buttons)

    def _handle_updown_round(self, choice: str) -> Dict:
        """업다운 라운드 진행"""
        result = GameService.play_updown_round(self.db, self.kakao_id, choice)

        if not result["success"]:
            return self._game_failure_response(result["message"])

        prev = result["prev_number"]
        next_num = result["next_number"]
        arrow = "📈" if next_num > prev else "📉"

        if result["won"]:
            round_mult = result["round_multiplier"]
            total_mult = result["total_multiplier"]
            current_round = result["round"]
            potential = result["potential_winnings"]

            # 연승 이펙트
            rounds_won = current_round - 1
            if rounds_won >= 5:
                streak_effect = "🔥🔥🔥 연승의 달인! 🔥🔥🔥"
            elif rounds_won >= 3:
                streak_effect = "🔥🔥 연승 중! 🔥🔥"
            elif rounds_won >= 2:
                streak_effect = "🔥 연승! 🔥"
            else:
                streak_effect = "✨ 적중! ✨"

            # 수수료 안내
            fee_notice = ""
            if current_round >= 4:
                from config import GameProbability
                for (start_r, end_r), rate in GameProbability.UPDOWN_ROUND_FEE.items():
                    if start_r <= current_round <= end_r:
                        pct = int((1 - rate) * 100)
                        if pct > 0:
                            fee_notice = f"\n⚡ 라운드 수수료: 배율 -{pct}%"
                        break

            msg = f"""🔢 업다운 — 라운드 {current_round - 1}

{arrow} {prev} → {next_num}
🎯 예측: {result['choice']} — {streak_effect}

이번 배율: x{round_mult}
📊 누적 배율: x{total_mult}

💰 투자금: {result['bet']:,}원
💎 현재 가치: {potential:,}원 (+{potential - result['bet']:,}원){fee_notice}

다음 숫자가 {next_num}보다 높을까? 낮을까?"""

            buttons = []
            up_mult = result["up_multiplier"]
            down_mult = result["down_multiplier"]

            if result["can_up"]:
                buttons.append({"label": f"📈 상승 (x{up_mult})", "action": "message", "messageText": "/업다운 상승"})
            if result["can_down"]:
                buttons.append({"label": f"📉 하락 (x{down_mult})", "action": "message", "messageText": "/업다운 하락"})
            buttons.append({"label": f"💰 정산 ({potential:,}원)", "action": "message", "messageText": "/업다운정산"})

            return KakaoResponse.quick_replies(msg, buttons)
        else:
            # 실패
            if abs(next_num - prev) <= 3:
                fail_msg = "😱 아슬아슬하게 빗나갔어요!"
            elif abs(next_num - prev) <= 10:
                fail_msg = "😤 아깝다!"
            else:
                fail_msg = "💨 빗나갔어요"

            msg = f"""🔢 업다운 — 게임 오버!

{arrow} {prev} → {next_num}
🎯 예측: {result['choice']} / 정답: {result['actual']}

{fail_msg}

💸 투자금 손실: -{result['bet']:,}원
💵 잔고: {result['cash']:,}원"""

            return KakaoResponse.quick_replies(
                msg,
                [
                    {"label": "🔢 다시 도전!", "action": "message", "messageText": f"/업다운 {result['bet']}"},
                    {"label": "🔮 시장예측", "action": "message", "messageText": f"/시장예측 {GameConfig.DEFAULT_BET}"},
                    {"label": "🚀 급등주", "action": "message", "messageText": "/급등"}
                ]
            )

    def handle_updown_cashout(self) -> Dict:
        """업다운 중간 정산"""
        result = GameService.cashout_updown(self.db, self.kakao_id)

        if not result["success"]:
            return self._game_failure_response(result["message"])

        profit = result["profit"]
        rounds = result["rounds"]

        if profit > 0:
            profit_text = f"📈 +{profit:,}원"
            if result["multiplier"] >= 5:
                effect = "🎆🎇 미친 정산! 🎆🎇"
            elif result["multiplier"] >= 3:
                effect = "🎉 훌륭한 정산! 🎉"
            elif result["multiplier"] >= 2:
                effect = "✨ 좋은 정산! ✨"
            else:
                effect = "💰 정산 완료!"
        else:
            profit_text = f"📉 {profit:,}원"
            effect = "💰 정산 완료!"

        is_big_cashout = result["multiplier"] >= 3  # 3배 이상 정산 = 대박

        msg = f"""🔢 업다운 — 정산!

{effect}

🎯 맞춘 횟수: {rounds}라운드
📊 최종 배율: x{result['multiplier']}

💰 투자금: {result['bet']:,}원
💎 수령액: {result['winnings']:,}원
{profit_text}

💵 잔고: {result['cash']:,}원"""

        buttons = [
            {"label": "🔢 다시 도전!", "action": "message", "messageText": f"/업다운 {result['bet']}"},
        ]
        # 대박 정산 시 랭킹 버튼 추가
        if is_big_cashout:
            buttons.append({"label": "🏆 랭킹 확인", "action": "message", "messageText": "/랭킹"})
        buttons.extend([
            {"label": "🔮 시장예측", "action": "message", "messageText": f"/시장예측 {GameConfig.DEFAULT_BET}"},
            {"label": "🚀 급등주", "action": "message", "messageText": "/급등"}
        ])

        return KakaoResponse.quick_replies(msg, buttons)

    def _updown_status_response(self, status: Dict) -> Dict:
        """업다운 진행 상태 응답"""
        number = status["number"]
        up_mult = status["up_multiplier"]
        down_mult = status["down_multiplier"]
        potential = status["potential_winnings"]

        msg = f"""🔢 업다운 — 진행 중!

🎲 현재 숫자: {number}
📊 라운드: {status['round']}
💎 누적 배율: x{status['multiplier']}
💰 투자금: {status['bet']:,}원
💎 현재 가치: {potential:,}원

다음 숫자가 {number}보다 높을까? 낮을까?"""

        buttons = []
        if status["can_up"]:
            buttons.append({"label": f"📈 상승 (x{up_mult})", "action": "message", "messageText": "/업다운 상승"})
        if status["can_down"]:
            buttons.append({"label": f"📉 하락 (x{down_mult})", "action": "message", "messageText": "/업다운 하락"})
        if status["round"] >= 2:
            buttons.append({"label": f"💰 정산 ({potential:,}원)", "action": "message", "messageText": "/업다운정산"})

        return KakaoResponse.quick_replies(msg, buttons)

    def _updown_active_game_response(self, result: Dict) -> Dict:
        """이미 진행중인 업다운 게임 알림"""
        return KakaoResponse.quick_replies(
            result["message"],
            [
                {"label": "📈 상승", "action": "message", "messageText": "/업다운 상승"},
                {"label": "📉 하락", "action": "message", "messageText": "/업다운 하락"},
                {"label": "💰 정산", "action": "message", "messageText": "/업다운정산"},
            ]
        )

    # ==========================================
    # 각성 시스템 (투자 감각 각성)
    # ==========================================

    def handle_enhance(self) -> Dict:
        """각성 — 정보 보기 또는 각성 시도"""
        parts = self.utterance.split()

        # /각성 시도 → 실제 각성 실행
        if len(parts) >= 2 and parts[1] in ["시도", "도전", "각성하기", "강화하기"]:
            return self._do_enhance()

        # /각성 → 정보 + 각성 버튼
        return self._show_enhance_info()

    def _show_enhance_info(self) -> Dict:
        """각성 정보 표시"""
        result = EnhanceService.get_enhance_info(self.db, self.kakao_id)

        if not result["success"]:
            return self._game_failure_response(result["message"])

        level = result["level"]
        title_name = result["title_name"]
        title_emoji = result["title_emoji"]
        att_mult = result["attendance_multiplier"]
        lot_mult = result["lottery_multiplier"]

        # 보너스 계산
        att_bonus = int((att_mult - 1) * 100)
        lot_bonus = int((lot_mult - 1) * 100)

        # 레벨 게이지 바
        gauge = self._make_gauge(level, EnhanceConfig.MAX_LEVEL)

        msg = f"""{title_emoji} {title_name}

🧬 각성 레벨: Lv.{level} / {EnhanceConfig.MAX_LEVEL}
{gauge}

📈 출석 보상 보너스: +{att_bonus}%
🎫 복권 보상 보너스: +{lot_bonus}%"""

        buttons = []

        if result.get("max_reached"):
            msg += "\n\n👑 최고 경지 도달! 이 톡방에서 당신을 넘을 사람은 없습니다."
            buttons = [
                {"label": "📅 출석", "action": "message", "messageText": "/출석"},
                {"label": "🎫 복권", "action": "message", "messageText": "/복권"},
            ]
        else:
            cost = result["next_cost"]
            rate = result["next_success_rate"]
            fail_prob = result.get("fail_drop_prob", 0)
            next_name = result.get("next_title_name", title_name)
            next_emoji = result.get("next_title_emoji", title_emoji)

            # 위험도 표시
            if fail_prob == 0:
                risk = "🟢 안전 (실패해도 레벨 유지)"
            elif fail_prob <= 30:
                risk = f"🟡 주의 (실패 시 {fail_prob}% 확률로 하락)"
            elif fail_prob <= 50:
                risk = f"🟠 위험 (실패 시 {fail_prob}% 확률로 하락)"
            else:
                risk = "🔴 극한 (실패 시 레벨 하락)"

            msg += f"""

📋 다음 각성 정보:
💰 비용: {cost:,}원
🎯 성공률: {rate}%
{risk}

{next_emoji} 성공 시 → {next_name} Lv.{level + 1}"""

            can_afford = result["cash"] >= cost
            if can_afford:
                buttons.append(
                    {"label": f"🧬 각성하기 ({cost:,}원)", "action": "message", "messageText": "/각성 시도"}
                )
            else:
                msg += f"\n\n❌ 잔고 부족 (보유: {result['cash']:,}원)"

        buttons.extend([
            {"label": "📅 출석", "action": "message", "messageText": "/출석"},
            {"label": "📈 예측게임", "action": "message", "messageText": "/예측"},
        ])

        return KakaoResponse.quick_replies(msg, buttons)

    def _do_enhance(self) -> Dict:
        """실제 각성 실행"""
        result = EnhanceService.attempt_enhance(self.db, self.kakao_id)

        if not result["success"]:
            return self._game_failure_response(result["message"])

        old_lv = result["old_level"]
        new_lv = result["new_level"]
        cost = result["cost"]
        rate = result["success_rate"]

        if result["enhanced"]:
            # 성공 — 레벨 구간별 극적 연출
            new_emoji = result["new_emoji"]
            new_name = result["new_title"]

            if result["title_changed"]:
                evolution_msg = f"\n\n🆙 칭호 승급!\n{result['old_emoji']} {result['old_title']} → {new_emoji} {new_name}"
            else:
                evolution_msg = ""

            att_bonus = int((result["attendance_multiplier"] - 1) * 100)
            lot_bonus = int((result["lottery_multiplier"] - 1) * 100)

            # 성공 연출 — 레벨/확률별 다르게
            if new_lv >= 20:
                header = "👑 만렙 달성! 전무후무한 경지!"
                effect = "🎆🎇🎆🎇🎆"
                flavor = "이 톡방의 전설로 기록됩니다."
            elif new_lv >= 16:
                header = f"⚡ Lv.{new_lv} 돌파! 이건 실력이다!"
                effect = "✨🎉✨🎉✨"
                flavor = f"성공률 {rate}%를 뚫었어요. 대단합니다."
            elif new_lv >= 10:
                header = f"🔥 Lv.{new_lv} 각성 성공!"
                effect = "🎊✨🎊"
                flavor = "여기서부터 진짜 시작입니다."
            elif new_lv >= 5:
                header = f"✨ Lv.{new_lv} 각성 성공!"
                effect = "🎊✨"
                flavor = "성장의 속도가 붙고 있어요."
            else:
                header = f"✨ Lv.{new_lv} 각성 성공!"
                effect = "✨"
                flavor = "좋은 출발이에요!"

            msg = f"""{effect}
{header}

{new_emoji} {new_name} Lv.{old_lv} → Lv.{new_lv}
🎯 성공률 {rate}%에서 성공!
💬 {flavor}{evolution_msg}

📈 출석 보너스: +{att_bonus}%
🎫 복권 보너스: +{lot_bonus}%

💰 사용: -{cost:,}원
💵 잔고: {result['cash']:,}원"""

        else:
            # 실패 — 공감+자극하는 연출
            drop = result.get("drop", 0)
            new_emoji = result["new_emoji"]
            new_name = result["new_title"]

            if drop > 0:
                drop_msg = f"💥 레벨 하락! Lv.{old_lv} → Lv.{new_lv} (-{drop})"
                if drop >= 2:
                    flavor = f"Lv.{old_lv}의 벽이 만만치 않네요... 하지만 올라갔었다는 건, 다시 올라갈 수 있다는 뜻!"
                else:
                    flavor = "한 발 물러났지만, 두 발 전진할 차례예요."
            else:
                drop_msg = f"🛡️ 레벨 유지! Lv.{old_lv}"
                flavor = "레벨은 지켰어요. 다시 도전하면 됩니다."

            # 실패 연출 — 성공률에 따라 아까움 차등
            if rate <= 10:
                header = f"😤 {rate}%의 벽..."
                miss_comment = f"확률 {rate}%... 이건 뚫는 사람이 진짜 괴물이에요."
            elif rate <= 30:
                header = "💨 아슬아슬하게 빗나갔다!"
                miss_comment = f"성공률 {rate}%, 분명 가능한 확률이었는데..."
            elif rate <= 50:
                header = "💨 이번엔 운이 안 따랐어요"
                miss_comment = f"성공률 {rate}%면 반반인데, 다음엔 내 차례!"
            else:
                header = "💨 에이, 이게 왜 실패야!"
                miss_comment = f"성공률 {rate}%에서 빠지다니... 다음엔 반드시!"

            msg = f"""{header}

{new_emoji} {new_name}
{drop_msg}
💬 {miss_comment}

{flavor}

💰 사용: -{cost:,}원
💵 잔고: {result['cash']:,}원"""

        # 다시 각성 가능 여부 체크
        buttons = []
        if new_lv < EnhanceConfig.MAX_LEVEL:
            next_cost = EnhanceConfig.get_cost(new_lv)
            if result["cash"] >= next_cost:
                buttons.append(
                    {"label": f"🧬 다시 각성! ({next_cost:,}원)", "action": "message", "messageText": "/각성 시도"}
                )
            buttons.append({"label": "🧬 각성 정보", "action": "message", "messageText": "/각성"})

        # 칭호 승급이나 고레벨 달성 시 랭킹 버튼
        if result["enhanced"] and (result.get("title_changed") or new_lv >= 10):
            buttons.append({"label": "🧬 각성 랭킹", "action": "message", "messageText": "/각성랭킹"})
        else:
            buttons.append({"label": "📈 예측게임", "action": "message", "messageText": "/예측"})

        buttons.append({"label": "🚀 급등주", "action": "message", "messageText": "/급등"})

        return KakaoResponse.quick_replies(msg, buttons)

    @staticmethod
    def _generate_quiz_lesson(quiz: dict) -> str:
        """역사 퀴즈 결과에서 투자 교훈 생성"""
        desc = quiz.get("description", "")
        answer = quiz["answer"]
        stock = quiz["stock_name"]

        # 키워드 기반 투자 교훈 매칭
        lessons = {
            "반도체": "📖 반도체는 사이클 산업! 호황→불황이 반복되므로 업황 전환점을 읽는 게 핵심이에요.",
            "메모리": "📖 메모리 반도체는 DRAM/NAND 가격 흐름이 주가를 좌우해요. 공급 과잉 시그널을 주시하세요.",
            "AI": "📖 AI는 2023~2024 최대 테마! 실적이 뒷받침되는 AI주와 테마만 탄 주식을 구분하는 게 중요해요.",
            "HBM": "📖 HBM(고대역폭메모리)은 AI 학습에 필수! AI 투자가 커질수록 HBM 수요도 증가해요.",
            "코로나": "📖 위기는 곧 기회! 코로나 폭락장에서 매수한 투자자들이 큰 수익을 거뒀어요.",
            "금리": "📖 금리 인상기에는 성장주(기술주)가 약세, 가치주가 강세인 경향이 있어요.",
            "전기차": "📖 전기차 시장은 정책(IRA, 보조금)에 민감해요. 정책 방향을 먼저 읽는 게 핵심!",
            "배터리": "📖 2차전지는 전기차 시장과 함께 움직여요. 원자재(리튬·니켈) 가격도 체크하세요.",
            "바이오": "📖 바이오주는 임상 결과와 기대감에 크게 요동쳐요. 실적보다 뉴스에 반응하는 섹터!",
            "IPO": "📖 공모주는 상장 직후 과열되기 쉬워요. 적정 밸류에이션을 냉정하게 따져보세요.",
            "규제": "📖 정부 규제 이슈는 주가에 직격타! 규제 리스크가 있는 기업은 정책 변화를 주시하세요.",
            "방산": "📖 방산주는 지정학 이슈에 민감해요. 국제 분쟁이 발생하면 방산 섹터가 주목받아요.",
            "언택트": "📖 사회 변화가 산업 트렌드를 바꿔요. 코로나 때 언택트, AI 시대엔 반도체가 수혜!",
            "철강": "📖 철강은 대표적인 경기 민감주! 글로벌 경기와 중국 수요에 크게 좌우돼요.",
            "커머스": "📖 플랫폼 기업은 이용자 수와 거래액이 핵심 지표! 성장률 둔화 시그널에 주의하세요.",
        }

        # 키워드 매칭 — 첫 번째 매칭되는 교훈 사용
        for keyword, lesson in lessons.items():
            if keyword in desc:
                return lesson

        # 기본 교훈 — 상승/하락에 따른 일반적 인사이트
        if answer == "상승":
            return f"📖 {stock}의 상승에는 분명한 이유가 있었어요. 실적·테마·정책 중 하나가 동력이었답니다."
        else:
            return "📖 하락에도 패턴이 있어요. 과열 후 조정, 실적 악화, 외부 악재 — 이 세 가지가 대부분이에요."

    @staticmethod
    def _make_gauge(current: int, maximum: int, length: int = 10) -> str:
        """레벨 게이지 바 생성"""
        filled = int((current / maximum) * length) if maximum > 0 else 0
        empty = length - filled
        bar = "▰" * filled + "▱" * empty
        return f"[{bar}] {current}/{maximum}"
