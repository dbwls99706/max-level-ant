"""
소셜/경쟁 관련 핸들러
- 랭킹, 배틀, 챌린지, 마일스톤
- 업적, 미션
"""
from typing import Dict

from services import (
    UserService, RankingService, MissionService,
    BattleService, ChallengeService, MilestoneService, AssetService
)
from utils import KakaoResponse, get_rival_msg
from config import GameConfig

from .base_handler import BaseHandlerMixin


class SocialHandlerMixin(BaseHandlerMixin):
    """소셜/경쟁 관련 핸들러 믹스인"""

    def handle_ranking(self) -> Dict:
        """랭킹 조회"""
        rankings = RankingService.get_ranking(self.db, limit=10)

        if not rankings:
            return KakaoResponse.quick_replies(
                "아직 랭킹 데이터가 없습니다.\n먼저 시작해서 첫 번째 랭커가 되어보세요!",
                [
                    {"label": "🚀 시작하기", "action": "message", "messageText": "/시작"},
                    {"label": "📈 급등주", "action": "message", "messageText": "/급등"}
                ]
            )

        ranking_list = ""
        my_rank_in_top10 = None
        total_users = len(rankings)

        for r in rankings:
            medal = ""
            if r["rank"] == 1:
                medal = "🥇"
            elif r["rank"] == 2:
                medal = "🥈"
            elif r["rank"] == 3:
                medal = "🥉"
            else:
                medal = f"{r['rank']}."

            emoji = "📈" if r["profit_rate"] >= 0 else "📉"

            # 각성 칭호 표시
            enhance_emoji = r.get("enhance_emoji", "")
            enhance_lv = r.get("enhance_level", 0)
            enhance_tag = f" {enhance_emoji}Lv.{enhance_lv}" if enhance_lv > 0 else ""

            # 본인 하이라이트
            is_me = r.get("kakao_id") == self.kakao_id
            if is_me:
                my_rank_in_top10 = r["rank"]
                ranking_list += f"\n{medal} ★{r['nickname']}★{enhance_tag} ← 나!"
            else:
                ranking_list += f"\n{medal} {r['nickname']}{enhance_tag}"
            ranking_list += f"\n   {emoji} {r['profit_rate']:+.2f}% ({r['total_asset']:,}원)\n"

        # 톡방 전체 유저 수 표기
        header = f"🏆 수익률 랭킹 (총 {total_users}명)\n"
        msg = header + ranking_list

        # TOP 10 안에 있으면 축하 메시지
        if my_rank_in_top10:
            msg = f"🎉 축하해요! {my_rank_in_top10}위!\n\n" + msg
        else:
            # TOP 10 밖이면 내 순위 + 바로 윗순위 경쟁자 표시
            my_rank = RankingService.get_my_rank(self.db, self.kakao_id)
            if my_rank:
                msg += "\n━━━━━━━━━━━━━━━━━"
                msg += f"\n📍 내 순위: {my_rank['rank']}위 / {my_rank['total']}명"
                msg += f"\n   📊 {my_rank['profit_rate']:+.2f}%"
                if my_rank.get("above_nickname"):
                    gap = (my_rank.get("above_profit_rate", 0) or 0) - my_rank["profit_rate"]
                    rival = get_rival_msg(my_rank["rank"], my_rank["above_nickname"], gap)
                    if rival:
                        msg += f"\n{rival}"

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "📍 내 순위", "action": "message", "messageText": "/내순위"},
                {"label": "🧬 각성 랭킹", "action": "message", "messageText": "/각성랭킹"},
                {"label": "📈 급등주", "action": "message", "messageText": "/급등"}
            ]
        )

    def handle_my_rank(self) -> Dict:
        """내 순위 조회"""
        rank_info = RankingService.get_my_rank(self.db, self.kakao_id)

        if rank_info is None:
            return KakaoResponse.quick_replies(
                "먼저 /시작 으로 참가하세요.",
                [{"label": "🚀 시작하기", "action": "message", "messageText": "/시작"}]
            )

        rank = rank_info["rank"]
        total = rank_info["total"]
        profit_rate = rank_info["profit_rate"]

        # 퍼센타일 계산
        percentile = ((total - rank + 1) / total) * 100 if total > 0 else 0

        # 순위 기반 동기부여 메시지
        if rank == 1:
            motivation = "👑 당신이 1위! 만렙개미 최강자!"
        elif rank <= 3:
            motivation = f"🏆 TOP 3! 정상까지 {rank - 1}명 남았어요!"
        elif percentile >= 90:
            motivation = f"🌟 상위 {100 - percentile:.0f}%! 거의 다 왔어요!"
        elif percentile >= 70:
            motivation = f"📈 상위 {100 - percentile:.0f}%! 좋은 성적이에요!"
        elif percentile >= 50:
            motivation = f"💪 상위 {100 - percentile:.0f}%! 조금만 더 분발!"
        else:
            motivation = f"🔥 {rank}위! 역전의 기회는 있어요!"

        # 수익률 기반 이모지
        rate_emoji = "📈" if profit_rate >= 0 else "📉"

        # 바로 윗순위 경쟁자 표시
        rival_line = ""
        if rank_info.get("above_nickname"):
            gap = (rank_info.get("above_profit_rate", 0) or 0) - profit_rate
            rival_line = "\n" + get_rival_msg(rank, rank_info["above_nickname"], gap)

        msg = f"""📍 내 순위

🏆 {rank}위 / 전체 {total}명
{rate_emoji} 수익률: {profit_rate:+.2f}%
💰 총 자산: {rank_info['total_asset']:,}원

{motivation}{rival_line}"""

        buttons = [
            {"label": "🏆 랭킹", "action": "message", "messageText": "/랭킹"},
            {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"},
            {"label": "📈 급등주", "action": "message", "messageText": "/급등"},
        ]

        return KakaoResponse.quick_replies(msg, buttons)

    def handle_enhance_ranking(self) -> Dict:
        """각성 랭킹 조회"""
        rankings = RankingService.get_enhance_ranking(self.db, limit=10)

        if not rankings:
            return KakaoResponse.quick_replies(
                "🧬 아직 각성한 개미가 없습니다.\n장 마감 후 각성에 도전해보세요!",
                [
                    {"label": "🧬 각성", "action": "message", "messageText": "/각성"},
                    {"label": "🏆 랭킹", "action": "message", "messageText": "/랭킹"}
                ]
            )

        ranking_list = ""
        my_rank = None

        for r in rankings:
            medal = ""
            if r["rank"] == 1:
                medal = "🥇"
            elif r["rank"] == 2:
                medal = "🥈"
            elif r["rank"] == 3:
                medal = "🥉"
            else:
                medal = f"{r['rank']}."

            is_me = r.get("kakao_id") == self.kakao_id
            if is_me:
                my_rank = r["rank"]
                ranking_list += f"\n{medal} ★{r['nickname']}★ ← 나!"
            else:
                ranking_list += f"\n{medal} {r['nickname']}"
            ranking_list += f"\n   {r['enhance_emoji']} {r['enhance_title']} Lv.{r['enhance_level']}\n"

        msg = f"🧬 각성 랭킹\n{ranking_list}"

        if my_rank:
            msg = f"🎉 각성 랭킹 {my_rank}위! 개미계 강자!\n\n" + msg

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "🏆 랭킹", "action": "message", "messageText": "/랭킹"},
                {"label": "🧬 각성", "action": "message", "messageText": "/각성"},
                {"label": "📍 내 순위", "action": "message", "messageText": "/내순위"}
            ]
        )

    def handle_mission(self) -> Dict:
        """일간 미션 현황"""
        user = UserService.get_user(self.db, self.kakao_id)
        if not user:
            return KakaoResponse.quick_replies(
                "먼저 /시작 으로 참가하세요.",
                [{"label": "🚀 시작하기", "action": "message", "messageText": "/시작"}]
            )

        status = MissionService.get_mission_status(self.db, self.kakao_id)
        mission = status["daily_mission"]

        bonus_text = ""
        if status["is_bonus_day"]:
            bonus_text = f"\n\n🎉 오늘은 보너스 요일! (보상 {status['bonus_multiplier']}배)"

        if mission["completed"]:
            mission_status = "✅ 퀘스트 완료!"
        else:
            mission_status = f"{mission['progress']}/{mission['target']}회"

        msg = f"""📋 오늘의 미션{bonus_text}

🎯 오늘의 퀘스트: {GameConfig.DAILY_MISSION_TRADE_COUNT}회 거래하기
📊 진행 현황: {mission_status}
🪙 퀘스트 보상: {mission['reward']:,}원

📈 총 거래 횟수: {status['total_trades']:,}회
💵 누적 실현 수익: {status['total_profit_realized']:,}원"""

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "🏆 업적", "action": "message", "messageText": "/업적"},
                {"label": "📊 인기 종목", "action": "message", "messageText": "/인기"}
            ]
        )

    def handle_achievements(self) -> Dict:
        """업적 현황"""
        user = UserService.get_user(self.db, self.kakao_id)
        if not user:
            return KakaoResponse.quick_replies(
                "먼저 /시작 으로 참가하세요.",
                [{"label": "🚀 시작하기", "action": "message", "messageText": "/시작"}]
            )

        status = MissionService.get_mission_status(self.db, self.kakao_id)

        msg = f"""🏆 업적
달성: {status['achievements_completed']}/{status['achievements_total']}개

"""
        if status["achievements"]:
            msg += "✅ 달성한 업적\n"
            for ach in status["achievements"]:
                msg += f"{ach['icon']} {ach['name']}\n"
            msg += "\n"

        if status["available_achievements"]:
            msg += "🎯 도전 중인 업적\n"
            for ach in status["available_achievements"][:3]:
                msg += f"⬜ {ach['name']}: {ach['description']}\n"
                msg += f"   보상: {ach['reward']:,}원\n"

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "📋 오늘의 미션", "action": "message", "messageText": "/미션"},
                {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
            ]
        )

    def handle_nickname(self) -> Dict:
        """닉네임 설정"""
        parts = self.utterance.split(maxsplit=1)

        user = UserService.get_user(self.db, self.kakao_id)
        if not user:
            return KakaoResponse.quick_replies(
                "먼저 /시작 으로 게임을 시작해주세요.",
                [{"label": "🎮 게임 시작", "action": "message", "messageText": "/시작"}]
            )

        if len(parts) < 2:
            current = user.nickname if user.nickname else "없음"
            return KakaoResponse.simple_text(
                f"🏷️ 닉네임 설정\n\n현재 닉네임: {current}\n\n사용법: /닉네임 [새 닉네임]\n예: /닉네임 투자왕"
            )

        new_nickname = parts[1].strip()

        # UserService.update_nickname에서 검증, 중복 확인, 변경 횟수 체크를 모두 처리

        success, msg = UserService.update_nickname(self.db, self.kakao_id, new_nickname)

        if not success:
            return KakaoResponse.simple_text(msg)

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "🏆 랭킹", "action": "message", "messageText": "/랭킹"},
                {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
            ]
        )

    # ==========================================
    # 배틀 시스템
    # ==========================================

    def handle_battle_help(self) -> Dict:
        """배틀 설명"""
        msg = """⚔️ 주가 배틀

🎯 배틀이란?
다른 개미와 주가 예측 대결!
종목의 주가가 오를지 내릴지 예측하세요.

📝 배틀 진행 방식
1. 도전자가 종목/예측/골드로 배틀 생성
2. 상대 개미가 배틀에 참가 (반대 방향 예측)
3. 60분 후 주가 변동으로 승패 결정
4. 승리한 개미가 골드 x2 획득!

💡 예시
• 도전자: 삼성전자 "상승" 예측 (10만 골드)
• 상대방: 삼성전자 "하락" 예측 (10만 골드)
• 60분 후 삼성전자가 올랐다면 → 도전자 승리!
• 승자는 20만 골드 획득 🎉

⚠️ 주의사항
• 한 번 생성/참가하면 취소 불가
• 여러 배틀 동시 참여 가능
• 무승부 시 골드 반환

📋 배틀 명령어
/배틀 [종목] [상승/하락] [금액] - 생성
/배틀참가 [ID] - 참가
/배틀결과 [ID] - 결과 확인
/배틀목록 - 대기 중인 배틀"""

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "⚔️ 배틀생성", "action": "message", "messageText": "/배틀"},
                {"label": "📋 배틀목록", "action": "message", "messageText": "/배틀목록"}
            ]
        )

    def handle_battle_create(self) -> Dict:
        """배틀 생성"""
        parts = self.utterance.split()

        if len(parts) < 3:
            default_bet = GameConfig.DEFAULT_BATTLE_BET
            top = self._get_top_popular_stock()
            if top:
                battle_btn = {"label": f"⚔️ {top} 상승", "action": "message", "messageText": f"/배틀 {top} 상승 {default_bet}"}
            else:
                battle_btn = {"label": "📊 인기종목", "action": "message", "messageText": "/인기"}
            return KakaoResponse.quick_replies(
                f"⚔️ 주가 배틀 생성\n\n사용법: /배틀 [종목] [상승/하락] [금액]\n예: /배틀 삼성전자 상승 {default_bet}\n\n❓ /배틀설명 으로 자세한 설명 확인",
                [
                    {"label": "❓ 배틀설명", "action": "message", "messageText": "/배틀설명"},
                    battle_btn,
                    {"label": "📋 배틀목록", "action": "message", "messageText": "/배틀목록"}
                ]
            )

        stock_name = parts[1]
        prediction = parts[2]
        bet = GameConfig.DEFAULT_BATTLE_BET
        if len(parts) >= 4:
            try:
                bet = int(parts[3].replace(",", ""))
            except ValueError:
                pass

        result = BattleService.create_battle(
            self.db, self.kakao_id, stock_name, prediction, bet
        )

        if not result["success"]:
            return KakaoResponse.simple_text(result["message"])

        msg = f"""⚔️ 배틀 생성 완료!

📊 종목: {result['stock_name']}
💰 현재가: {result['current_price']:,}원
{result['pred_emoji']} 내 예측: {result['prediction']}
🪙 투입 골드: {result['bet_amount']:,}원
⏱️ 결판 시간: {result['duration']}분

🆔 배틀 ID: {result['battle_id']}

⏳ 상대 개미 대기 중...
다른 개미가 '/배틀참가 {result['battle_id']}'로 참가하면 배틀 시작!

⚠️ 생성 후 취소 불가"""

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "📋 배틀목록", "action": "message", "messageText": "/배틀목록"},
                {"label": "⚔️ 추가 배틀", "action": "message", "messageText": "/배틀"}
            ]
        )

    def handle_battle_join(self) -> Dict:
        """배틀 참가"""
        parts = self.utterance.split()

        if len(parts) < 2:
            return KakaoResponse.quick_replies(
                "⚔️ 배틀 참가\n\n사용법: /배틀참가 [배틀ID]\n예: /배틀참가 1",
                [{"label": "📋 배틀목록", "action": "message", "messageText": "/배틀목록"}]
            )

        try:
            battle_id = int(parts[1])
        except ValueError:
            return KakaoResponse.simple_text("배틀 ID는 숫자입니다.")

        result = BattleService.join_battle(self.db, self.kakao_id, battle_id)

        if not result["success"]:
            return KakaoResponse.simple_text(result["message"])

        msg = f"""⚔️ 배틀 시작!
━━━━━━━━━━━━━━━━━
📊 {result['stock_name']} | 시작가 {result['start_price']:,}원

🔵 {result['challenger_name']} → 📈{result['challenger_prediction']}!
  ⚡ VS ⚡
🔴 {result['opponent_name']} → 📉{result['opponent_prediction']}!

🪙 승자 골드: {result['bet_amount'] * 2:,}원
⏱️ {result['duration']}분 뒤 승자 결정!
━━━━━━━━━━━━━━━━━
어느 개미가 이길까?! /배틀결과 {result['battle_id']}"""

        return KakaoResponse.quick_replies(
            msg,
            [{"label": "📊 결과확인", "action": "message", "messageText": f"/배틀결과 {result['battle_id']}"}]
        )

    def handle_battle_result(self) -> Dict:
        """배틀 결과 확인"""
        parts = self.utterance.split()

        if len(parts) < 2:
            return KakaoResponse.simple_text("사용법: /배틀결과 [배틀ID]")

        try:
            battle_id = int(parts[1])
        except ValueError:
            return KakaoResponse.simple_text("배틀 ID는 숫자입니다.")

        result = BattleService.check_battle_result(self.db, battle_id)

        if not result["success"]:
            return KakaoResponse.simple_text(result["message"])

        if result.get("finished"):
            change_emoji = "📈" if result["price_change"] >= 0 else "📉"

            market_note = ""
            if result.get("market_closed"):
                market_note = "\n⏰ (장 마감으로 조기 종료)"

            if result['winner'] == "무승부":
                result_header = "🤝 무승부!"
                result_detail = "주가 변동 없음 — 투자금 반환"
            else:
                result_header = f"🎊 배틀 종료!{market_note}"
                result_detail = f"🏆 승자: {result['winner']}! 예측 적중!"

            msg = f"""⚔️ 배틀 결과
━━━━━━━━━━━━━━━━━
{result_header}

📊 {result['stock_name']}
💰 {result['start_price']:,}원 → {result['end_price']:,}원
{change_emoji} {result['price_change']:+,}원 ({result['change_rate']:+.2f}%)

🔵 {result['challenger_name']} vs 🔴 {result['opponent_name']}
━━━━━━━━━━━━━━━━━
{result_detail}
💰 상금 {result['prize']:,}원 획득!

다음 도전자는?! ⚔️"""

            return KakaoResponse.quick_replies(
                msg,
                [
                    {"label": "⚔️ 새 배틀", "action": "message", "messageText": "/배틀"},
                    {"label": "📋 배틀목록", "action": "message", "messageText": "/배틀목록"},
                    {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
                ]
            )

        return KakaoResponse.simple_text(result["message"])

    def handle_battle_list(self) -> Dict:
        """대기 중인 배틀 목록"""
        battles = BattleService.get_waiting_battles(self.db)

        if not battles:
            return KakaoResponse.quick_replies(
                "⚔️ 대기 중인 배틀이 없습니다.\n새로운 배틀을 시작해보세요!",
                [
                    {"label": "⚔️ 배틀생성", "action": "message", "messageText": "/배틀"},
                    {"label": "🚀 급등주", "action": "message", "messageText": "/급등"}
                ]
            )

        msg = f"⚔️ 대기 중인 배틀 ({len(battles)}건)\n도전장이 날아왔다!\n"
        buttons = []
        for b in battles[:5]:
            pred_emoji = "📈" if b["prediction"] == "상승" else "📉"
            msg += f"\n🆔 #{b['id']} | {b['challenger']}의 도전!"
            msg += f"\n   {b['stock_name']} {pred_emoji}{b['prediction']} | 💰 상금 {b['bet_amount'] * 2:,}원\n"

            if len(buttons) < 3:
                buttons.append({
                    "label": f"⚔️ #{b['id']} 참가",
                    "action": "message",
                    "messageText": f"/배틀참가 {b['id']}"
                })

        buttons.append({"label": "⚔️ 새 배틀", "action": "message", "messageText": "/배틀"})

        return KakaoResponse.quick_replies(msg, buttons)

    # ==========================================
    # 주간 챌린지
    # ==========================================

    def handle_challenge(self) -> Dict:
        """주간 챌린지 현황"""
        result = ChallengeService.get_user_challenge_progress(self.db, self.kakao_id)

        if not result["success"]:
            return KakaoResponse.simple_text(result["message"])

        ch = result["challenge"]
        pr = result["progress"]

        progress_bar = "▓" * int(pr["progress_rate"] / 10) + "░" * (10 - int(pr["progress_rate"] / 10))

        status = "✅ 완료!" if pr["completed"] else f"{pr['current']}/{pr['target']}"
        reward_status = "(수령완료)" if pr["reward_claimed"] else ""

        msg = f"""🎯 주간 챌린지

{ch['description']}

📊 진행: [{progress_bar}] {pr['progress_rate']:.0f}%
🎯 상태: {status} {reward_status}
💰 보상: {ch['reward']:,}원

📅 기간: {ch['start_date']} ~ {ch['end_date']}"""

        buttons = []
        if pr["completed"] and not pr["reward_claimed"]:
            buttons.append({"label": "🎁 보상받기", "action": "message", "messageText": "/챌린지보상"})

        buttons.extend([
            {"label": "🏆 마일스톤", "action": "message", "messageText": "/마일스톤"},
            {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
        ])

        return KakaoResponse.quick_replies(msg, buttons)

    def handle_challenge_reward(self) -> Dict:
        """챌린지 보상 수령"""
        result = ChallengeService.claim_challenge_reward(self.db, self.kakao_id)

        if not result["success"]:
            return KakaoResponse.simple_text(result["message"])

        msg = f"""🎉 챌린지 보상 수령!

💰 +{result['reward']:,}원
💵 현재 잔고: {result['cash']:,}원"""

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "🎯 챌린지", "action": "message", "messageText": "/챌린지"},
                {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
            ]
        )

    # ==========================================
    # 마일스톤
    # ==========================================

    def handle_milestone(self) -> Dict:
        """마일스톤 현황"""
        user = UserService.get_user(self.db, self.kakao_id)
        if not user:
            return KakaoResponse.quick_replies(
                "먼저 /시작 으로 게임을 시작해주세요.",
                [{"label": "🎮 게임 시작", "action": "message", "messageText": "/시작"}]
            )

        result = MilestoneService.get_user_milestones(self.db, self.kakao_id)

        msg = f"""🏆 마일스톤

✅ 달성: {len(result['achieved'])}개
⬜ 미달성: {len(result['pending'])}개
"""

        if result["unclaimed_rewards"] > 0:
            msg += f"🎁 미수령 보상: {result['unclaimed_rewards']:,}원\n"

        if result["achieved"]:
            msg += "\n✅ 최근 달성\n"
            for m in result["achieved"][-3:]:
                claimed = "✓" if m["reward_claimed"] else "🎁"
                msg += f"  {m['name']} {claimed}\n"

        if result["pending"]:
            msg += "\n🎯 다음 목표\n"
            for m in result["pending"][:2]:
                msg += f"  {m['name']}\n"
                msg += f"    {m['description']} (보상: {m['reward']:,}원)\n"

        buttons = []
        if result["unclaimed_rewards"] > 0:
            buttons.append({"label": "🎁 전체 보상받기", "action": "message", "messageText": "/마일스톤보상"})

        buttons.extend([
            {"label": "🎯 챌린지", "action": "message", "messageText": "/챌린지"},
            {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
        ])

        return KakaoResponse.quick_replies(msg, buttons)

    def handle_milestone_reward(self) -> Dict:
        """마일스톤 보상 수령"""
        result = MilestoneService.claim_all_rewards(self.db, self.kakao_id)

        if not result["success"]:
            return KakaoResponse.simple_text(result["message"])

        msg = f"""🎉 마일스톤 보상 수령!

💰 +{result['total_reward']:,}원 ({result['count']}개)
💵 현재 잔고: {result['cash']:,}원

달성 마일스톤:
"""
        for m in result["milestones"]:
            msg += f"  ✅ {m}\n"

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "🏆 마일스톤", "action": "message", "messageText": "/마일스톤"},
                {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
            ]
        )

    # ==========================================
    # 자산 차트
    # ==========================================

    def handle_asset_chart(self) -> Dict:
        """자산 차트 조회"""
        user = UserService.get_user(self.db, self.kakao_id)
        if not user:
            return KakaoResponse.quick_replies(
                "먼저 /시작 으로 게임을 시작해주세요.",
                [{"label": "🎮 게임 시작", "action": "message", "messageText": "/시작"}]
            )

        AssetService.record_daily_asset(self.db, self.kakao_id)
        chart = AssetService.generate_ascii_chart(self.db, self.kakao_id, days=7)
        summary = AssetService.get_asset_summary(self.db, self.kakao_id)

        msg = f"📊 내 자산 차트 (7일)\n\n{chart}"

        if summary.get("has_history") and summary.get("changes"):
            msg += "\n\n📈 기간별 변동"
            if "day" in summary["changes"]:
                d = summary["changes"]["day"]
                emoji = "🔺" if d["amount"] >= 0 else "🔻"
                msg += f"\n  어제대비: {d['amount']:+,}원 ({d['rate']:+.1f}%) {emoji}"

            if "week" in summary["changes"]:
                w = summary["changes"]["week"]
                emoji = "🔺" if w["amount"] >= 0 else "🔻"
                msg += f"\n  주간: {w['amount']:+,}원 ({w['rate']:+.1f}%) {emoji}"

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"},
                {"label": "🏆 랭킹", "action": "message", "messageText": "/랭킹"}
            ]
        )
