"""
보상 파이프라인 회귀 테스트
- AssetService.get_total_asset (자산 마일스톤 판정 기반)
- 자산/스트릭 마일스톤 지급
- millionaire 업적 평가
- 주간 챌린지 진행도 배선 (카운트형/지표형)
- 출석 이벤트의 업적/마일스톤/챌린지 트리거
"""

from unittest.mock import patch

from models import Holding, Milestone, WeeklyChallenge, UserChallenge
from services.asset_service import AssetService
from services.milestone_service import MilestoneService
from services.mission_service import MissionService
from services.challenge_service import ChallengeService
from services.user_service import UserService


class TestGetTotalAsset:
    """AssetService.get_total_asset — 존재하지 않던 메서드 복구"""

    def test_cash_only(self, db, test_user):
        """보유 주식이 없으면 현금이 곧 총자산"""
        with patch(
            "services.asset_service.StockService.batch_get_prices", return_value={}
        ):
            total = AssetService.get_total_asset(db, test_user.kakao_id)
        assert total == test_user.cash

    def test_with_holdings(self, db, test_user):
        """보유 주식 평가액 합산 (시세 조회 실패 시 평단가 폴백)"""
        holding = Holding(
            kakao_id=test_user.kakao_id,
            stock_code="005930",
            stock_name="삼성전자",
            quantity=10,
            avg_price=60_000,
            total_invested=600_000,
        )
        db.add(holding)
        db.commit()

        with patch(
            "services.asset_service.StockService.batch_get_prices",
            return_value={"005930": 70_000},
        ):
            total = AssetService.get_total_asset(db, test_user.kakao_id)
        assert total == test_user.cash + 70_000 * 10

        # 시세 조회 실패 → 평단가 사용
        with patch(
            "services.asset_service.StockService.batch_get_prices", return_value={}
        ):
            total = AssetService.get_total_asset(db, test_user.kakao_id)
        assert total == test_user.cash + 60_000 * 10

    def test_unknown_user(self, db):
        assert AssetService.get_total_asset(db, "no_such_user") is None


class TestMilestones:
    """수익/스트릭 마일스톤 지급 복구"""

    def test_profit_milestone_awarded(self, db, test_user):
        """수익금 기준 마일스톤 자동 지급"""
        achieved = MilestoneService.check_milestones(
            db, test_user.kakao_id, total_profit=10_000_000
        )
        types = {m["type"] for m in achieved}
        assert "ASSET_10M" in types

        # 중복 지급 없음
        again = MilestoneService.check_milestones(
            db, test_user.kakao_id, total_profit=10_000_000
        )
        assert all(m["type"] != "ASSET_10M" for m in again)

    def test_no_profit_no_milestone(self, db, test_user):
        """수익이 없으면(초기 자금 그대로) 수익 마일스톤 미지급"""
        achieved = MilestoneService.check_milestones(
            db, test_user.kakao_id, total_profit=0
        )
        assert all(m["type"] != "ASSET_10M" for m in achieved)

    def test_streak_milestone_awarded(self, db, test_user):
        """연속 출석 마일스톤 자동 지급"""
        achieved = MilestoneService.check_milestones(db, test_user.kakao_id, streak=7)
        types = {m["type"] for m in achieved}
        assert "STREAK_7" in types

        milestone = (
            db.query(Milestone)
            .filter(
                Milestone.kakao_id == test_user.kakao_id,
                Milestone.milestone_type == "STREAK_7",
            )
            .first()
        )
        assert milestone is not None


class TestMillionaireAchievement:
    """millionaire 업적 평가 복구"""

    def test_millionaire_awarded_with_total_profit(self, db, test_user):
        new_achievements = MissionService.check_and_award_achievements(
            db, test_user.kakao_id, total_profit=100_000_000
        )
        ids = {a["id"] for a in new_achievements}
        assert "millionaire" in ids

    def test_millionaire_not_awarded_below_threshold(self, db, test_user):
        new_achievements = MissionService.check_and_award_achievements(
            db, test_user.kakao_id, total_profit=99_999_999
        )
        ids = {a["id"] for a in new_achievements}
        assert "millionaire" not in ids


def _force_challenge(db, challenge_type: str, target: int, reward: int = 1_000_000):
    """이번 주 챌린지를 특정 타입으로 고정"""
    week_id = ChallengeService.get_current_week_id()
    from datetime import date

    challenge = WeeklyChallenge(
        week_id=week_id,
        challenge_type=challenge_type,
        target_value=target,
        description=f"테스트 챌린지 {challenge_type}",
        reward=reward,
        start_date=date(2000, 1, 1),
        end_date=date(2100, 1, 1),
    )
    db.add(challenge)
    db.commit()
    return challenge


class TestChallengeWiring:
    """주간 챌린지 진행도 배선 (기존에는 어디서도 갱신되지 않던 죽은 기능)"""

    def test_count_challenge_progress(self, db, test_user):
        """카운트형 챌린지 진행 및 완료"""
        challenge = _force_challenge(db, "TRADE_COUNT", target=2)

        result = ChallengeService.update_challenge_progress(
            db, test_user.kakao_id, "TRADE_COUNT"
        )
        assert result is None  # 아직 미완료

        result = ChallengeService.update_challenge_progress(
            db, test_user.kakao_id, "TRADE_COUNT"
        )
        assert result is not None and result["completed"] is True

        uc = (
            db.query(UserChallenge)
            .filter(
                UserChallenge.kakao_id == test_user.kakao_id,
                UserChallenge.challenge_id == challenge.id,
            )
            .first()
        )
        assert uc.completed == 1

        # 완료 후 보상 수령 가능
        claim = ChallengeService.claim_challenge_reward(db, test_user.kakao_id)
        assert claim["success"] is True

    def test_type_mismatch_is_noop(self, db, test_user):
        """챌린지 타입이 다르면 진행도 갱신 없음"""
        challenge = _force_challenge(db, "ATTENDANCE", target=3)
        ChallengeService.update_challenge_progress(
            db, test_user.kakao_id, "TRADE_COUNT"
        )
        uc = (
            db.query(UserChallenge)
            .filter(UserChallenge.challenge_id == challenge.id)
            .first()
        )
        assert uc is None or uc.current_value == 0

    def test_asset_growth_challenge(self, db, test_user):
        """지표형 챌린지 (자산 증가) — 주 시작 자산 대비 만원 단위"""
        challenge = _force_challenge(db, "ASSET_GROWTH", target=100)  # 100만원 증가

        # 기준선: 기록이 없으므로 initial_cash(1000만원) 사용
        total_asset = test_user.initial_cash + 1_500_000  # +150만원
        result = ChallengeService.update_asset_challenges(
            db, test_user.kakao_id, total_asset
        )
        assert result is not None and result["completed"] is True

        uc = (
            db.query(UserChallenge)
            .filter(UserChallenge.challenge_id == challenge.id)
            .first()
        )
        assert uc.current_value >= 100

    def test_profit_rate_challenge(self, db, test_user):
        """지표형 챌린지 (수익률 %)"""
        _force_challenge(db, "PROFIT_RATE", target=10)

        total_asset = int(test_user.initial_cash * 1.12)  # +12%
        result = ChallengeService.update_asset_challenges(
            db, test_user.kakao_id, total_asset
        )
        assert result is not None and result["completed"] is True

    def test_negative_growth_is_noop(self, db, test_user):
        """자산이 줄었으면 진행도 갱신 없음"""
        _force_challenge(db, "ASSET_GROWTH", target=100)
        result = ChallengeService.update_asset_challenges(
            db, test_user.kakao_id, test_user.initial_cash - 1_000_000
        )
        assert result is None


class TestAttendanceRewardWiring:
    """출석 이벤트가 업적/마일스톤/챌린지를 트리거하는지"""

    def test_attendance_awards_streak_rewards(self, db, test_user):
        """7일 연속 출석 도달 시 업적(streak_7)과 마일스톤(STREAK_7) 지급"""
        from datetime import datetime, timedelta
        from config import KST

        today = datetime.now(KST).date()
        test_user.attendance_streak = 6
        test_user.last_attendance = today - timedelta(days=1)
        db.commit()

        with (
            patch(
                "services.asset_service.StockService.batch_get_prices", return_value={}
            ),
            patch("services.user_service.log_attendance"),
        ):
            success, reward, streak, cash, _ = UserService.check_attendance(
                db, test_user.kakao_id
            )

        assert success is True
        assert streak == 7

        # 마일스톤 지급 확인
        milestone = (
            db.query(Milestone)
            .filter(
                Milestone.kakao_id == test_user.kakao_id,
                Milestone.milestone_type == "STREAK_7",
            )
            .first()
        )
        assert milestone is not None

        # 업적 지급 확인
        db.refresh(test_user)
        assert "streak_7" in (test_user.achievements or "")

        # 반환된 잔고는 보상 반영 후 값 (출석 보상 + 업적/마일스톤 보상)
        assert cash > test_user.initial_cash

    def test_attendance_updates_attendance_challenge(self, db, test_user):
        """출석 시 개근왕 챌린지 진행"""
        challenge = _force_challenge(db, "ATTENDANCE", target=3)

        with (
            patch(
                "services.asset_service.StockService.batch_get_prices", return_value={}
            ),
            patch("services.user_service.log_attendance"),
        ):
            UserService.check_attendance(db, test_user.kakao_id)

        uc = (
            db.query(UserChallenge)
            .filter(
                UserChallenge.kakao_id == test_user.kakao_id,
                UserChallenge.challenge_id == challenge.id,
            )
            .first()
        )
        assert uc is not None
        assert uc.current_value == 1
