"""
MissionService 단위 테스트
- 일간 미션, 업적 달성
"""
from services.mission_service import MissionService, ACHIEVEMENTS
from config import GameConfig


class TestDailyMission:
    """일간 미션 테스트"""

    def test_initial_mission_state(self, db, test_user):
        status = MissionService.check_daily_mission(db, test_user.kakao_id)
        assert status["completed"] is False
        assert status["progress"] == 0
        assert status["target"] == GameConfig.DAILY_MISSION_TRADE_COUNT
        assert status["reward"] == GameConfig.DAILY_MISSION_REWARD

    def test_increment_trade_count(self, db, test_user):
        """거래 횟수 증가"""
        MissionService.increment_trade_count(db, test_user.kakao_id)
        db.refresh(test_user)
        assert test_user.daily_trade_count == 1
        assert test_user.total_trades == 1

    def test_mission_completion(self, db, test_user):
        """미션 완료 (목표 횟수 달성)"""
        reward_info = None
        for _ in range(GameConfig.DAILY_MISSION_TRADE_COUNT):
            reward_info = MissionService.increment_trade_count(db, test_user.kakao_id)

        assert reward_info is not None
        assert reward_info["reward"] >= GameConfig.DAILY_MISSION_REWARD

    def test_mission_not_completed_twice(self, db, test_user):
        """미션 중복 완료 방지"""
        for _ in range(GameConfig.DAILY_MISSION_TRADE_COUNT):
            MissionService.increment_trade_count(db, test_user.kakao_id)

        # 추가 거래 시 보상 없음
        extra_reward = MissionService.increment_trade_count(db, test_user.kakao_id)
        assert extra_reward is None


class TestAchievements:
    """업적 달성 테스트"""

    def test_first_trade_achievement(self, db, test_user):
        """첫 거래 업적"""
        test_user.total_trades = 1
        db.commit()

        new_achievements = MissionService.check_and_award_achievements(
            db, test_user.kakao_id
        )

        ids = [a["id"] for a in new_achievements]
        assert "first_trade" in ids

    def test_achievement_reward_granted(self, db, test_user):
        """업적 보상 지급"""
        initial_cash = test_user.cash
        test_user.total_trades = 1
        db.commit()

        MissionService.check_and_award_achievements(db, test_user.kakao_id)
        db.refresh(test_user)

        first_trade_reward = ACHIEVEMENTS["first_trade"]["reward"]
        assert test_user.cash == initial_cash + first_trade_reward

    def test_achievement_not_duplicated(self, db, test_user):
        """업적 중복 지급 방지"""
        test_user.total_trades = 1
        db.commit()

        first_result = MissionService.check_and_award_achievements(db, test_user.kakao_id)
        second_result = MissionService.check_and_award_achievements(db, test_user.kakao_id)

        assert len(first_result) >= 1
        first_ids = [a["id"] for a in first_result]
        second_ids = [a["id"] for a in second_result]
        # 이미 달성한 업적은 두 번 지급되지 않음
        for ach_id in first_ids:
            assert ach_id not in second_ids

    def test_profit_achievement(self, db, test_user):
        """수익 업적"""
        new_achievements = MissionService.check_and_award_achievements(
            db, test_user.kakao_id, trade_profit=1_000_000
        )

        ids = [a["id"] for a in new_achievements]
        assert "first_profit" in ids
        assert "profit_1m" in ids

    def test_get_user_achievements(self, db, test_user):
        """유저 업적 목록 조회"""
        test_user.total_trades = 10
        db.commit()
        MissionService.check_and_award_achievements(db, test_user.kakao_id)

        achievements = MissionService.get_user_achievements(db, test_user.kakao_id)
        assert len(achievements) > 0

    def test_get_available_achievements(self, db, test_user):
        """미달성 업적 목록"""
        available = MissionService.get_available_achievements(db, test_user.kakao_id)
        assert len(available) == len(ACHIEVEMENTS)  # 아무것도 달성 안 한 상태
