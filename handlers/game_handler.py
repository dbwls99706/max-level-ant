"""
예측게임 관련 핸들러
- 복권, 시장예측(역사 퀴즈), 업다운(멀티라운드), 각성(투자 감각 각성)
"""

from typing import Dict, List, Optional

from services import GameService
from services.collection_service import CollectionService
from services.enhance_service import EnhanceService
import enhance_classes as ec
from enhance_art import FAMILIES, RARITY_ART
from enhance_config import EnhanceConfig
from game_config import GameConfig
from settings import AssetConfig
from utils import KakaoResponse

from .base_handler import BaseHandlerMixin


class GameHandlerMixin(BaseHandlerMixin):
    """예측게임 관련 핸들러 믹스인"""

    def handle_game_menu(self) -> Dict:
        """예측 게임 메뉴"""
        msg = """예측 게임

/보물상자 - 무료 보물상자 (1일 5회)
/시장예측 [금액] - 과거 주가 예언 배틀
/업다운 [금액] - 숫자 도전 게임
/각성 - 캐릭터 각성. 언제든 가능

예언 배틀: 실제 역사 주가. 맞추면 2배, 틀리면 전멸
업다운: 연속으로 맞출수록 배율이 오릅니다
각성: 레벨을 올리면 출석·보물상자 보상이 늘어납니다
예언 배틀과 업다운은 장 마감 후 이용할 수 있습니다"""

        small_bet = GameConfig.DEFAULT_BET
        return KakaoResponse.text_with_buttons(
            msg,
            [
                {
                    "label": "보물상자",
                    "action": "message",
                    "messageText": "/보물상자",
                },
                {"label": "각성", "action": "message", "messageText": "/각성"},
                {
                    "label": f"⚡ {small_bet // 10000}만 예언 배틀",
                    "action": "message",
                    "messageText": f"/시장예측 {small_bet}",
                },
            ],
        )

    def handle_lottery(self) -> Dict:
        """복권 긁기"""
        result = GameService.play_lottery(self.db, self.kakao_id)

        if not result["success"]:
            bet = GameConfig.DEFAULT_BET
            return KakaoResponse.text_with_buttons(
                result["message"],
                [
                    {
                        "label": "예언 배틀",
                        "action": "message",
                        "messageText": f"/시장예측 {bet}",
                    },
                    {
                        "label": "업다운",
                        "action": "message",
                        "messageText": f"/업다운 {bet}",
                    },
                    {"label": "📈 급등주", "action": "message", "messageText": "/급등"},
                ],
            )

        tier = result["tier"]
        reward = result["reward"]
        remaining = result.get("remaining", 0)
        is_big_win = tier in ("전설", "영웅")

        # 희귀도별 연출 (10명+ 톡방에서 주목받는 이펙트)
        # 등급 색 칩(🟠🟣🔵🟢)은 남긴다. 등급을 한눈에 구분하는 정보고,
        # 옆에 붙던 🎆🎇 같은 축포 줄은 아무것도 말하지 않아 걷어냈다.
        if tier == "전설":
            effect = "🟠 전설 등급 획득!"
            reveal = "스르르... 번쩍!"
        elif tier == "영웅":
            effect = "🟣 영웅 등급"
            reveal = "스르르... 오!"
        elif tier == "희귀":
            effect = "🔵 희귀 등급"
            reveal = "스르르... 오"
        elif tier == "고급":
            effect = "🟢 고급 등급"
            reveal = "스르르..."
        else:
            effect = ""
            reveal = "스르르..."

        # 남은 횟수 - 긴급성 연출
        if remaining == 0:
            remaining_msg = "오늘 보물상자를 모두 썼습니다"
        elif remaining == 1:
            remaining_msg = "마지막 1회 남음"
        else:
            remaining_msg = f"오늘 남은 횟수 {remaining}회"

        reward_text = f"+{reward:,}원" if reward > 0 else "0원"

        # 각성 보너스 표시
        enhance_bonus = result.get("enhance_bonus", 0)
        enhance_line = ""
        if enhance_bonus > 0:
            enhance_line = (
                f"\n캐릭터 보너스 +{enhance_bonus:,}원"
                f" (Lv.{result.get('enhance_level', 0)})"
            )

        # Near-miss 아까움 연출 (꽝일 때)
        near_miss_line = ""
        near_miss_tier = result.get("near_miss_tier")
        if near_miss_tier and reward == 0:
            near_miss_reward = result.get("near_miss_reward", 0)
            near_miss_line = (
                f"\n\n아깝다. {near_miss_tier}"
                f" ({near_miss_reward:,}원)까지 한 끗 차이였습니다"
            )

        name = self._display_name()
        msg = f"""{name}의 보물상자... {reveal}

{effect}
{result["message"]}

획득 골드 {reward_text}{enhance_line}{near_miss_line}

{remaining_msg}
현재 골드 {result["cash"]:,}원"""

        buttons = []
        if remaining > 0:
            buttons.append(
                {
                    "label": "한번 더",
                    "action": "message",
                    "messageText": "/보물상자",
                }
            )
        if is_big_win:
            buttons.append(
                {
                    "label": "포트폴리오",
                    "action": "message",
                    "messageText": "/포트폴리오",
                }
            )
            buttons.append(
                {"label": "랭킹", "action": "message", "messageText": "/랭킹"}
            )
        else:
            buttons.append(
                {
                    "label": "예언 배틀",
                    "action": "message",
                    "messageText": f"/시장예측 {GameConfig.DEFAULT_BET}",
                }
            )
            buttons.append(
                {"label": "📈 급등주", "action": "message", "messageText": "/급등"}
            )

        return KakaoResponse.text_with_buttons(msg, buttons)

    # ==========================================
    # 시장예측 (역사 퀴즈)
    # ==========================================

    def handle_stock_quiz(self) -> Dict:
        """시장예측 - 역사 퀴즈"""
        parts = self.utterance.split()

        if len(parts) < 2:
            return KakaoResponse.text_with_buttons(
                "과거 주가 예언 배틀\n\n"
                "실제 역사 주가 종목이 출제됩니다.\n"
                "📈 상승과 📉 하락 중에 고르세요.\n"
                "맞추면 베팅한 골드의 2배, 틀리면 전액을 잃습니다.\n\n"
                "사용법: /시장예측 [금액]\n"
                "예: /시장예측 100000",
                [
                    {
                        "label": "5만 예언!",
                        "action": "message",
                        "messageText": "/시장예측 50000",
                    },
                    {
                        "label": "10만 배팅!",
                        "action": "message",
                        "messageText": "/시장예측 100000",
                    },
                    {
                        "label": "50만 올인!",
                        "action": "message",
                        "messageText": "/시장예측 500000",
                    },
                ],
            )

        try:
            bet = int(parts[1].replace(",", ""))
        except ValueError:
            return KakaoResponse.text_with_buttons(
                "골드 금액을 숫자로 입력해주세요.\n예: /시장예측 100000",
                [
                    {
                        "label": "5만 예언!",
                        "action": "message",
                        "messageText": "/시장예측 50000",
                    },
                    {
                        "label": "10만 배팅!",
                        "action": "message",
                        "messageText": "/시장예측 100000",
                    },
                ],
            )

        # 선택지가 없으면 퀴즈 출제 (상승/하락 선택 유도)
        if len(parts) < 3:
            result = GameService.issue_stock_quiz(self.db, self.kakao_id, bet)
            if not result["success"]:
                from errors import ErrorCode

                if result.get("error_code") == ErrorCode.MARKET_CLOSED:
                    return self._market_closed_response(result["message"])
                return self._game_failure_response(result["message"])
            return self._quiz_issued_response(result)

        # 선택지가 있으면 정답 확인
        # (판정은 서버가 출제해 저장한 퀴즈로만 - 메시지로 퀴즈를 지정할 수 없음)
        choice = parts[2].strip()
        result = GameService.answer_stock_quiz(self.db, self.kakao_id, choice)

        if not result["success"]:
            from errors import ErrorCode

            # 출제된 퀴즈가 없으면 새로 출제해서 안내
            if result.get("error_code") == ErrorCode.INVALID_STATE:
                issued = GameService.issue_stock_quiz(self.db, self.kakao_id, bet)
                if issued["success"]:
                    return self._quiz_issued_response(issued)
            if result.get("error_code") == ErrorCode.MARKET_CLOSED:
                return self._market_closed_response(result["message"])
            return self._game_failure_response(result["message"])

        quiz = result["quiz"]

        if result["won"]:
            if result["profit"] >= 500_000:
                effect = "💥⚡ 예언 적중! 대박 골드 폭발!"
            else:
                effect = "예언 적중. 골드 2배 획득"
            profit_text = f"📈 +{result['profit']:,}원"
            encourage = "역사를 꿰뚫는 개미의 눈! 왜 맞았는지 아래 해설을 확인해봐요 🔍"
        else:
            effect = "빗나갔습니다. 베팅한 골드를 잃었습니다"
            profit_text = f"{result['profit']:,}원"
            encourage = "아래 당시 상황을 읽으면 다음엔 맞출 수 있습니다"

        answer_emoji = "📈" if quiz["answer"] == "상승" else "📉"

        # 투자 교훈 생성 - 역사 데이터 기반 맥락 제공
        lesson = self._generate_quiz_lesson(quiz)

        name = self._display_name()
        msg = f"""{name}의 과거 주가 예언 배틀

{quiz["stock_name"]} · {quiz["period"]}

{answer_emoji} 정답 {quiz["answer"]}
내 선택 {result["choice"]}

{effect}
{encourage}

왜 이런 움직임이었을까
{quiz["description"]}

투자 인사이트
{lesson}

베팅 {result["bet"]:,}원 / 손익 {profit_text}
현재 골드 {result["cash"]:,}원"""

        if result["won"]:
            buttons = [
                {
                    "label": "다시 예언!",
                    "action": "message",
                    "messageText": f"/시장예측 {bet}",
                },
                {
                    # 직전 베팅의 2배를 건다. '올인'은 전 재산을 건다는 뜻이라
                    # 실제 동작과 다른 이름이었다.
                    "label": "베팅 2배로",
                    "action": "message",
                    "messageText": f"/시장예측 {bet * 2}",
                },
                {
                    "label": "포트폴리오",
                    "action": "message",
                    "messageText": "/포트폴리오",
                },
                {"label": "📈 급등주", "action": "message", "messageText": "/급등"},
            ]
            if result["bet"] >= 500_000:
                buttons[2] = {
                    "label": "랭킹",
                    "action": "message",
                    "messageText": "/랭킹",
                }
        else:
            buttons = [
                {
                    "label": "다시 예언!",
                    "action": "message",
                    "messageText": f"/시장예측 {bet}",
                },
                {
                    "label": "보물상자",
                    "action": "message",
                    "messageText": "/보물상자",
                },
                {"label": "📈 급등주", "action": "message", "messageText": "/급등"},
            ]

        return KakaoResponse.text_with_buttons(msg, buttons)

    def _quiz_issued_response(self, result: Dict) -> Dict:
        """시장예측 퀴즈 출제 응답 (정답 힌트인 당시 이슈는 결과에서만 공개)"""
        quiz = result["quiz"]
        bet = result["bet"]

        header = "예언 배틀 시작"
        if result.get("reissued"):
            header = "진행 중인 예언 배틀이 있습니다\n(먼저 이 퀴즈에 답해주세요)"

        return KakaoResponse.text_with_buttons(
            f"{header}\n\n"
            f"{quiz['stock_name']} · {quiz['period']}\n\n"
            f"이 기간 주가는 올랐을까, 내렸을까?\n"
            f"당시 이슈는 결과 발표 때 공개됩니다.\n"
            f"맞추면 {bet * 2:,}원, 틀리면 전액을 잃습니다.",
            [
                {
                    "label": "📈 상승!",
                    "action": "message",
                    "messageText": f"/시장예측 {bet} 상승",
                },
                {
                    "label": "📉 하락!",
                    "action": "message",
                    "messageText": f"/시장예측 {bet} 하락",
                },
            ],
        )

    # ==========================================
    # 업다운 (멀티라운드)
    # ==========================================

    def handle_updown(self) -> Dict:
        """업다운 게임 - 시작 또는 라운드 진행"""
        parts = self.utterance.split()

        # /업다운 만 입력한 경우
        if len(parts) == 1:
            # 진행중인 게임이 있는지 확인
            status = GameService.get_updown_status(self.db, self.kakao_id)
            if status.get("active"):
                return self._updown_status_response(status)

            return KakaoResponse.text_with_buttons(
                "🔢 업다운 - 숫자 예측 게임!\n\n"
                "1~100 숫자가 나오면\n"
                "다음 숫자가 높을지 낮을지 예측!\n\n"
                "✅ 맞추면: 배율 누적, 계속 도전!\n"
                "❌ 틀리면: 투자금 전액 손실!\n"
                "💰 정산: 원할 때 수익 확정!\n\n"
                "사용법: /업다운 [금액]",
                [
                    {
                        "label": "5만원",
                        "action": "message",
                        "messageText": "/업다운 50000",
                    },
                    {
                        "label": "10만원",
                        "action": "message",
                        "messageText": "/업다운 100000",
                    },
                    {
                        "label": "50만원",
                        "action": "message",
                        "messageText": "/업다운 500000",
                    },
                ],
            )

        # /업다운 [상승/하락] - 진행중인 게임의 라운드 진행
        if len(parts) == 2 and not parts[1].replace(",", "").isdigit():
            choice = parts[1]
            return self._handle_updown_round(choice)

        # /업다운 [금액] - 새 게임 시작
        try:
            bet = int(parts[1].replace(",", ""))
        except ValueError:
            return KakaoResponse.text_with_buttons(
                "투자금은 숫자로 입력해주세요.\n예: /업다운 50000",
                [
                    {
                        "label": "5만원",
                        "action": "message",
                        "messageText": "/업다운 50000",
                    },
                    {
                        "label": "10만원",
                        "action": "message",
                        "messageText": "/업다운 100000",
                    },
                ],
            )

        # /업다운 [금액] [상승/하락] - 새 게임은 금액만, 라운드는 별도
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

        name = self._display_name()
        msg = f"""🔢 {name}의 업다운 시작!

🎲 첫 번째 숫자: {number}

다음 숫자가 {number}보다 높을까? 낮을까?

📈 상승 선택 시 배율: x{up_mult}
📉 하락 선택 시 배율: x{down_mult}

🪙 투입 골드: {result["bet"]:,}원
💰 현재 골드: {result["cash"]:,}원"""

        buttons = []
        if result["can_up"]:
            buttons.append(
                {
                    "label": f"📈 상승 (x{up_mult})",
                    "action": "message",
                    "messageText": "/업다운 상승",
                }
            )
        if result["can_down"]:
            buttons.append(
                {
                    "label": f"📉 하락 (x{down_mult})",
                    "action": "message",
                    "messageText": "/업다운 하락",
                }
            )

        return KakaoResponse.text_with_buttons(msg, buttons)

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

            # 연승 이펙트 (톡방에서 주목받는 레벨)
            rounds_won = current_round - 1
            if rounds_won >= 7:
                streak_effect = "👑🔥🔥🔥 전설의 연승! 🔥🔥🔥👑"
            elif rounds_won >= 5:
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
                from game_config import GameProbability

                for (start_r, end_r), rate in GameProbability.UPDOWN_ROUND_FEE.items():
                    if start_r <= current_round <= end_r:
                        pct = int((1 - rate) * 100)
                        if pct > 0:
                            fee_notice = f"\n⚡ 라운드 수수료: 배율 -{pct}%"
                        break

            msg = f"""🔢 업다운 - 라운드 {current_round - 1}

{arrow} {prev} → {next_num}
🎯 예측: {result["choice"]} - {streak_effect}

이번 배율: x{round_mult}
📊 누적 배율: x{total_mult}

🪙 투입 골드: {result["bet"]:,}원
💎 현재 가치: {potential:,}원 (+{potential - result["bet"]:,}원){fee_notice}

다음 숫자가 {next_num}보다 높을까? 낮을까?"""

            buttons = []
            up_mult = result["up_multiplier"]
            down_mult = result["down_multiplier"]

            if result["can_up"]:
                buttons.append(
                    {
                        "label": f"📈 상승 (x{up_mult})",
                        "action": "message",
                        "messageText": "/업다운 상승",
                    }
                )
            if result["can_down"]:
                buttons.append(
                    {
                        "label": f"📉 하락 (x{down_mult})",
                        "action": "message",
                        "messageText": "/업다운 하락",
                    }
                )
            buttons.append(
                {
                    "label": f"💰 정산 ({potential:,}원)",
                    "action": "message",
                    "messageText": "/업다운정산",
                }
            )

            return KakaoResponse.text_with_buttons(msg, buttons)
        else:
            # 실패
            if abs(next_num - prev) <= 3:
                fail_msg = "😱 아슬아슬하게 빗나갔어요!"
            elif abs(next_num - prev) <= 10:
                fail_msg = "😤 아깝다!"
            else:
                fail_msg = "💨 빗나갔어요"

            name = self._display_name()
            msg = f"""🔢 {name}의 업다운 - 게임 오버!

{arrow} {prev} → {next_num}
🎯 예측: {result["choice"]} / 정답: {result["actual"]}

{fail_msg}

💸 골드 손실: -{result["bet"]:,}원
💰 현재 골드: {result["cash"]:,}원"""

            return KakaoResponse.text_with_buttons(
                msg,
                [
                    {
                        "label": "다시 도전!",
                        "action": "message",
                        "messageText": f"/업다운 {result['bet']}",
                    },
                    {
                        "label": "예언 배틀",
                        "action": "message",
                        "messageText": f"/시장예측 {GameConfig.DEFAULT_BET}",
                    },
                    {"label": "📈 급등주", "action": "message", "messageText": "/급등"},
                ],
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
            if result["multiplier"] >= 8:
                effect = "🎆🎇🎆🎇🎆\n━━━━━━━━━━━━━━━━━\n  ★ 대박! x{result['multiplier']} 정산! ★\n━━━━━━━━━━━━━━━━━"
            elif result["multiplier"] >= 5:
                effect = "🎆🎇 x{mult} 정산! 🎆🎇".format(mult=result["multiplier"])
            elif result["multiplier"] >= 3:
                effect = "🎉 x{mult} 훌륭한 정산! 🎉".format(mult=result["multiplier"])
            elif result["multiplier"] >= 2:
                effect = "✨ 좋은 정산! ✨"
            else:
                effect = "💰 정산 완료!"
        else:
            profit_text = f"📉 {profit:,}원"
            effect = "💰 정산 완료!"

        is_big_cashout = result["multiplier"] >= 3  # 3배 이상 정산 = 대박

        name = self._display_name()
        msg = f"""🔢 {name}의 업다운 - 정산!

{effect}

🎯 클리어 라운드: {rounds}라운드
📊 최종 배율: x{result["multiplier"]}

🪙 투입 골드: {result["bet"]:,}원
💎 수령 골드: {result["winnings"]:,}원
{profit_text}

💰 현재 골드: {result["cash"]:,}원"""

        buttons = [
            {
                "label": "다시 도전!",
                "action": "message",
                "messageText": f"/업다운 {result['bet']}",
            },
        ]
        # 대박 정산 시 랭킹 버튼 추가
        if is_big_cashout:
            buttons.append(
                {"label": "랭킹", "action": "message", "messageText": "/랭킹"}
            )
        buttons.extend(
            [
                {
                    "label": "예언 배틀",
                    "action": "message",
                    "messageText": f"/시장예측 {GameConfig.DEFAULT_BET}",
                },
                {"label": "📈 급등주", "action": "message", "messageText": "/급등"},
            ]
        )

        return KakaoResponse.text_with_buttons(msg, buttons)

    def _updown_status_response(self, status: Dict) -> Dict:
        """업다운 진행 상태 응답"""
        number = status["number"]
        up_mult = status["up_multiplier"]
        down_mult = status["down_multiplier"]
        potential = status["potential_winnings"]

        msg = f"""🔢 업다운 - 진행 중!

🎲 현재 숫자: {number}
📊 라운드: {status["round"]}
💎 누적 배율: x{status["multiplier"]}
🪙 투입 골드: {status["bet"]:,}원
💎 현재 가치: {potential:,}원

다음 숫자가 {number}보다 높을까? 낮을까?"""

        buttons = []
        if status["can_up"]:
            buttons.append(
                {
                    "label": f"📈 상승 (x{up_mult})",
                    "action": "message",
                    "messageText": "/업다운 상승",
                }
            )
        if status["can_down"]:
            buttons.append(
                {
                    "label": f"📉 하락 (x{down_mult})",
                    "action": "message",
                    "messageText": "/업다운 하락",
                }
            )
        if status["round"] >= 2:
            buttons.append(
                {
                    "label": f"💰 정산 ({potential:,}원)",
                    "action": "message",
                    "messageText": "/업다운정산",
                }
            )

        return KakaoResponse.text_with_buttons(msg, buttons)

    def _updown_active_game_response(self, result: Dict) -> Dict:
        """이미 진행중인 업다운 게임 알림"""
        return KakaoResponse.text_with_buttons(
            result["message"],
            [
                {
                    "label": "📈 상승",
                    "action": "message",
                    "messageText": "/업다운 상승",
                },
                {
                    "label": "📉 하락",
                    "action": "message",
                    "messageText": "/업다운 하락",
                },
                {"label": "정산", "action": "message", "messageText": "/업다운정산"},
            ],
        )

    # ==========================================
    # 각성 시스템 (던전 캐릭터 각성)
    # ==========================================

    def handle_enhance(self) -> Dict:
        """각성 - 정보 보기 또는 각성 시도"""
        parts = self.utterance.split()

        # /각성 시도 → 실제 각성 실행 (장 마감 후만 가능)
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

        # 직군·종 표시 (Lv.10 이상이고 배정 완료)
        class_line = ""
        if result.get("job_label"):
            class_line = (
                f"\n{result['family_emoji']} {result['family_name']} 계열"
                f"\n{result['job_label']}  {result['rarity_label']}"
                f" · {result['growth_name']}"
            )
            bonus = result.get("rarity_bonus") or 0
            if bonus:
                class_line += f"\n랭킹 수익률 +{bonus:g}%"
        elif level < EnhanceConfig.CLASS_LEVEL_THRESHOLD:
            remain = EnhanceConfig.CLASS_LEVEL_THRESHOLD - level
            class_line = (
                f"\nLv.{EnhanceConfig.CLASS_LEVEL_THRESHOLD}에서 직군 배정"
                f" (앞으로 {remain}레벨)"
            )

        name = self._display_name()
        msg = f"""{title_emoji} {name} - {title_name}

각성 레벨 Lv.{level} / {EnhanceConfig.MAX_LEVEL}
{gauge}{class_line}

출석 보상 +{att_bonus}%
보물상자 +{lot_bonus}%"""

        buttons = []

        if result.get("max_reached"):
            msg += "\n\n만렙 달성. 당신을 넘을 개미는 없습니다."
            buttons = [
                {"label": "출석", "action": "message", "messageText": "/출석"},
                {
                    "label": "보물상자",
                    "action": "message",
                    "messageText": "/보물상자",
                },
            ]
        else:
            cost = result["next_cost"]

            # 다음 칭호는 적지 않는다. 성공하기 전에 결과를 먼저 보여주면
            # 각성 버튼을 누를 이유가 절반 사라진다.
            msg += f"""

다음 각성
비용 {cost:,}원"""

            can_afford = result["cash"] >= cost
            if not can_afford:
                msg += f"\n골드 부족 (보유: {result['cash']:,}원)"
            else:
                buttons.append(
                    {
                        "label": "각성하기",
                        "action": "message",
                        "messageText": "/각성 시도",
                    }
                )

        buttons.extend(
            [
                {"label": "출석", "action": "message", "messageText": "/출석"},
                {"label": "예측 게임", "action": "message", "messageText": "/예측"},
            ]
        )

        return KakaoResponse.text_with_buttons(msg, buttons)

    def _do_enhance(self) -> Dict:
        """실제 각성 실행.

        시간 제한은 없다. 각성은 시세와 무관한 성장 요소라 장중에 막을
        이유가 없고, 막아두면 낮에 들어온 유저가 할 게 없어진다.
        관문은 비용뿐이고 그 돈은 주식으로 번다.
        """
        result = EnhanceService.attempt_enhance(self.db, self.kakao_id)

        if not result["success"]:
            return self._game_failure_response(result["message"])

        old_lv = result["old_level"]
        new_lv = result["new_level"]
        cost = result["cost"]

        if result["enhanced"]:
            # 성공 - 레벨별 고유 연출
            new_emoji = result["new_emoji"]
            new_name = result["new_title"]

            if result.get("job_assigned"):
                # 직군 배정 - 이 판의 정체성이 정해지는 순간
                evolution_msg = (
                    f"\n\n직군 배정\n"
                    f"{result['family_emoji']} {result['family_name']} 계열\n"
                    f"{result['job_label']}  {result['rarity_label']}"
                )
                bonus = result.get("rarity_bonus") or 0
                if bonus:
                    evolution_msg += f"\n랭킹 수익률 +{bonus:g}%"
            elif result.get("rarity_rerolled"):
                # 종 재추첨 - 올라갔는지 내려갔는지가 핵심이다
                delta = result.get("rarity_delta", 0)
                arrow = {1: "상승", -1: "하락", 0: "유지"}[delta]
                evolution_msg = (
                    f"\n\n종 재추첨 - {arrow}\n"
                    f"{result['job_label']}  {result['rarity_label']}"
                )
                bonus = result.get("rarity_bonus") or 0
                evolution_msg += f"\n랭킹 수익률 +{bonus:g}%"
            elif result.get("growth_changed") and result.get("job_label"):
                evolution_msg = (
                    f"\n\n{result['growth_name']} 단계 진입\n"
                    f"{result['job_label']}의 모습이 달라집니다."
                )
            elif result["title_changed"]:
                evolution_msg = (
                    f"\n\n{result['old_emoji']} {result['old_title']}"
                    f" → {new_emoji} {new_name}"
                )
            else:
                evolution_msg = ""

            att_bonus = int((result["attendance_multiplier"] - 1) * 100)
            lot_bonus = int((result["lottery_multiplier"] - 1) * 100)

            # 레벨별 고유 문구
            flavor = (
                EnhanceConfig.SUCCESS_FLAVORS[new_lv]
                if new_lv < len(EnhanceConfig.SUCCESS_FLAVORS)
                else ""
            )

            # 이펙트 - 레벨 구간별.
            # 만렙 판정은 MAX_LEVEL을 봐야 한다. 20으로 박아두면 만렙을
            # 30으로 올렸을 때 Lv.20에서 "만렙 달성"이라고 거짓말을 한다.
            # 예전에는 레벨 구간마다 🎆🎇🎆🎇🎆 같은 줄을 하나 더 붙였다.
            # 그 줄은 아무것도 말하지 않으면서 카드 본문 230자를 잡아먹고,
            # 정작 읽어야 할 문구를 아래로 밀어냈다.
            if new_lv >= EnhanceConfig.MAX_LEVEL:
                header = "만렙 개미 달성"
            else:
                header = f"Lv.{new_lv} 각성 성공"

            name = self._display_name()
            msg = f"""{header} - {name}

{new_emoji} {new_name} Lv.{old_lv} → Lv.{new_lv}
{flavor}{evolution_msg}

출석 보상 +{att_bonus}%
보물상자 +{lot_bonus}%

사용 -{cost:,}원
현재 골드 {result["cash"]:,}원"""

        else:
            # 실패 - 레벨 0으로 초기화 + 레벨별 고유 문구
            new_emoji = result["new_emoji"]
            new_name = result["new_title"]

            # 레벨별 고유 실패 문구
            fail_flavor = (
                EnhanceConfig.FAIL_FLAVORS[old_lv]
                if old_lv < len(EnhanceConfig.FAIL_FLAVORS)
                else ""
            )

            # 레벨 변화는 아래 "Lv.12 → Lv.0" 한 줄이 이미 말한다.
            # 거기에 "Lv.0 초기화!"를 덧붙이면 같은 사실을 두 번 외치는 꼴이다.
            if old_lv >= 15:
                header = f"Lv.{old_lv}의 빛이 꺼집니다"
                reset_msg = "쌓아온 모든 레벨이 사라집니다. 다시, 쪼렙 개미로."
            elif old_lv >= 10:
                header = f"Lv.{old_lv}에서 추락"
                reset_msg = "시장을 읽던 눈이 닫힙니다. 다시 백지의 쪼렙으로."
            elif old_lv >= 5:
                header = f"Lv.{old_lv}에서 실패"
                reset_msg = "익숙해진 시장 감각이 흐려집니다. 처음 그 날로."
            elif old_lv >= 1:
                header = "각성 실패"
                reset_msg = "짧은 성장이 리셋됩니다. 다시 쪼렙부터."
            else:
                header = "각성 실패"
                reset_msg = "잃을 레벨도 없었습니다."

            # 무엇을 잃었는지 이름으로 말해줘야 실패가 사건이 된다.
            # "Lv.12 → 0"만 보면 숫자가 줄어든 것으로만 읽힌다.
            lost_msg = ""
            if result.get("lost_job"):
                lost_msg = (
                    f"\n\n잃은 것: {result['lost_rarity']} {result['lost_job']}"
                    f"\n도감 기록은 그대로 남습니다."
                )

            name = self._display_name()
            level_line = f"Lv.{old_lv} → Lv.{new_lv}" if old_lv else f"Lv.{new_lv} 유지"
            msg = f"""{header} - {name}

{new_emoji} {new_name} {level_line}
{reset_msg}
{fail_flavor}{lost_msg}

사용 -{cost:,}원
현재 골드 {result["cash"]:,}원"""

        buttons = []
        if new_lv < EnhanceConfig.MAX_LEVEL:
            next_cost = EnhanceConfig.get_cost(new_lv)
            if result["cash"] >= next_cost:
                # 비용은 본문에 적는다. 버튼 라벨은 14자 한도라
                # 금액을 붙이면 잘려서 오히려 안 보인다.
                msg += f"\n\n다음 각성 비용 {next_cost:,}원"
                buttons.append(
                    {
                        "label": "다시 각성",
                        "action": "message",
                        "messageText": "/각성 시도",
                    }
                )
            buttons.append(
                {"label": "각성 정보", "action": "message", "messageText": "/각성"}
            )

        # 직업 승급이나 고레벨 달성 시 랭킹 버튼
        if result["enhanced"] and (result.get("title_changed") or new_lv >= 10):
            buttons.append(
                {
                    "label": "각성 랭킹",
                    "action": "message",
                    "messageText": "/각성랭킹",
                }
            )
        else:
            buttons.append(
                {"label": "예측 게임", "action": "message", "messageText": "/예측"}
            )

        buttons.append(
            {"label": "📈 급등주", "action": "message", "messageText": "/급등"}
        )

        return self._enhance_response(result, msg, buttons)

    def _enhance_response(self, result: Dict, msg: str, buttons: List[Dict]) -> Dict:
        """각성 결과를 이미지 카드로, 안 되면 텍스트로 응답한다.

        카카오 basicCard는 공개 HTTPS 절대 URL이 있어야 하고 설명이 230자로
        잘린다. PUBLIC_BASE_URL이 없거나 직군이 아직 없는 저레벨이면 이미지가
        없으므로 텍스트로 물러선다. 여기서 예외를 던지면 각성 자체가 실패한다.
        """
        stem = result.get("art_stem")
        image_url = AssetConfig.image_url(stem) if stem else ""
        if not image_url:
            return KakaoResponse.text_with_buttons(
                msg, buttons, button_cap=self.button_cap
            )

        level = result["new_level"]
        title = f"{result['new_emoji']} Lv.{level} {result['job_label']}"

        # 카드 본문은 짧아야 한다(230자). 수치는 텍스트 경로에 있고,
        # 카드에서는 그림과 그 그림을 설명하는 문장이 주인공이다.
        #
        # 다만 이번 각성에서 '무엇이 바뀌었는지'는 카드에도 있어야 한다.
        # 종이 올랐는지 내렸는지가 안 보이면 재추첨이 무작위 소음이 된다.
        lines = []
        if result.get("job_assigned"):
            lines.append("직군 배정")
        elif result.get("rarity_rerolled"):
            arrow = {1: "종 상승", -1: "종 하락", 0: "종 유지"}[
                result.get("rarity_delta", 0)
            ]
            lines.append(arrow)
        elif result.get("growth_changed"):
            lines.append(f"{result['growth_name']} 단계 진입")

        lines.append(f"{result['rarity_label']} · {result['growth_name']}")
        if result.get("flavor"):
            lines.append("")
            lines.append(result["flavor"])
        if result.get("newly_unlocked"):
            lines.append("")
            lines.append("도감 신규 해금")

        return KakaoResponse.basic_card(
            title,
            "\n".join(lines),
            image_url,
            buttons,
            button_cap=self.button_cap,
            image_size=AssetConfig.image_size(),
        )

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

        # 키워드 매칭 - 첫 번째 매칭되는 교훈 사용
        for keyword, lesson in lessons.items():
            if keyword in desc:
                return lesson

        # 기본 교훈 - 상승/하락에 따른 일반적 인사이트
        if answer == "상승":
            return f"📖 {stock}의 상승에는 분명한 이유가 있었어요. 실적·테마·정책 중 하나가 동력이었답니다."
        else:
            return "📖 하락에도 패턴이 있어요. 과열 후 조정, 실적 악화, 외부 악재 - 이 세 가지가 대부분이에요."

    # ==========================================
    # 도감
    # ==========================================

    def handle_collection(self) -> Dict:
        """도감 - 인자가 없으면 전체 요약, 있으면 계열 상세"""
        parts = self.utterance.split()
        if len(parts) >= 2:
            family = self._resolve_family(parts[1])
            if family:
                return self._collection_family(family)
            return KakaoResponse.text_with_buttons(
                f"'{parts[1]}' 계열을 찾을 수 없습니다.\n\n"
                + " / ".join(f"{e} {n}" for n, e in FAMILIES.values()),
                [{"label": "도감", "action": "message", "messageText": "/도감"}],
            )
        return self._collection_summary()

    @staticmethod
    def _resolve_family(word: str) -> Optional[str]:
        """유저가 친 한글 계열명(또는 영문 키)을 계열 키로"""
        word = word.strip()
        for key, (name, _emoji) in FAMILIES.items():
            if word in (key, name):
                return key
        return None

    def _collection_summary(self) -> Dict:
        summary = CollectionService.get_summary(self.db, self.kakao_id)
        gauge = self._make_gauge(summary["owned"], summary["total"], length=12)

        lines = []
        for key, (name, emoji) in FAMILIES.items():
            f = summary["by_family"][key]
            mark = "✅" if f["owned"] == f["total"] else "　"
            lines.append(f"{mark}{emoji} {name} {f['owned']}/{f['total']}")

        rarity_line = "  ".join(
            f"{RARITY_ART[r][1]}{summary['by_rarity'][r]}" for r in RARITY_ART
        )

        name = self._display_name()
        msg = f"""📖 {name}의 각성 도감

{gauge} ({summary["percent"]}%)
🎖️ 직군 {summary["jobs_owned"]}/{summary["jobs_total"]}종

{chr(10).join(lines)}

종별: {rarity_line}

💡 /도감 트레이더 처럼 계열을 붙이면 자세히 볼 수 있어요."""

        # 가장 많이 모은 계열을 바로 눌러볼 수 있게 한다
        best = max(FAMILIES, key=lambda k: summary["by_family"][k]["owned"])
        best_name = FAMILIES[best][0]
        return KakaoResponse.text_with_buttons(
            msg,
            [
                {
                    "label": f"📖 {best_name}"[:14],
                    "action": "message",
                    "messageText": f"/도감 {best_name}",
                },
                {"label": "각성", "action": "message", "messageText": "/각성"},
            ],
        )

    def _collection_family(self, family: str) -> Dict:
        detail = CollectionService.get_family_detail(self.db, self.kakao_id, family)
        name, emoji = FAMILIES[family]

        items = []
        for job in detail["jobs"]:
            if job["owned"] == 0:
                desc = "미발견"
                title = "❓ ???"
            else:
                best = job["best_rarity"]
                best_label = ec.rarity_label(best) if best else ""
                desc = f"{job['owned']}/{job['total']}칸 · 최고 {best_label}"
                title = job["label"]
            items.append({"title": title, "description": desc})

        return KakaoResponse.list_card(
            f"{emoji} {name} 계열 도감",
            items,
            [{"label": "전체 도감", "action": "message", "messageText": "/도감"}],
        )

    @staticmethod
    def _make_gauge(current: int, maximum: int, length: int = 10) -> str:
        """레벨 게이지 바 생성"""
        filled = int((current / maximum) * length) if maximum > 0 else 0
        empty = length - filled
        bar = "▰" * filled + "▱" * empty
        return f"[{bar}] {current}/{maximum}"
