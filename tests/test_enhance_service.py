"""
각성 시스템 (투자 감각 각성) 테스트
"""

import pytest
from unittest.mock import patch

from services.enhance_service import EnhanceService
from enhance_config import EnhanceConfig
from game_config import GameConfig


class TestEnhanceInfo:
    """각성 정보 조회 테스트"""

    def test_enhance_info_default_level(self, db, test_user):
        """초기 각성 레벨은 0"""
        result = EnhanceService.get_enhance_info(db, test_user.kakao_id)
        assert result["success"] is True
        assert result["level"] == 0
        valid_names = [t[0] for t in EnhanceConfig.TITLE_NAMES[0]]
        assert result["title_name"] in valid_names
        valid_emojis = [t[1] for t in EnhanceConfig.TITLE_NAMES[0]]
        assert result["title_emoji"] in valid_emojis

    def test_enhance_info_shows_next_cost(self, db, test_user):
        """다음 각성 비용이 표시됨"""
        result = EnhanceService.get_enhance_info(db, test_user.kakao_id)
        assert result["next_cost"] == EnhanceConfig.get_cost(0)
        assert result["next_success_rate"] == EnhanceConfig.get_success_rate(0)

    def test_enhance_info_with_level(self, db, test_user):
        """레벨이 있는 경우 정보 표시"""
        test_user.enhance_level = 10
        db.commit()

        result = EnhanceService.get_enhance_info(db, test_user.kakao_id)
        assert result["level"] == 10
        valid_names = [t[0] for t in EnhanceConfig.TITLE_NAMES[10]]
        assert result["title_name"] in valid_names
        assert result[
            "attendance_multiplier"
        ] == EnhanceConfig.get_attendance_multiplier(10)
        assert result["lottery_multiplier"] == EnhanceConfig.get_lottery_multiplier(10)

    def test_enhance_info_max_level(self, db, test_user):
        """만렙인 경우"""
        test_user.enhance_level = EnhanceConfig.MAX_LEVEL
        db.commit()

        result = EnhanceService.get_enhance_info(db, test_user.kakao_id)
        assert result["level"] == EnhanceConfig.MAX_LEVEL
        assert result.get("max_reached") is True

    def test_enhance_info_unknown_user(self, db):
        """존재하지 않는 유저"""
        result = EnhanceService.get_enhance_info(db, "nonexistent")
        assert result["success"] is False


class TestEnhanceAttempt:
    """각성 시도 테스트"""

    def test_enhance_success(self, db, test_user):
        """각성 성공 시 레벨 증가"""
        with patch(
            "services.enhance_service.random.randint", return_value=1
        ):  # 무조건 성공
            result = EnhanceService.attempt_enhance(db, test_user.kakao_id)

        assert result["success"] is True
        assert result["enhanced"] is True
        assert result["new_level"] == 1
        assert result["old_level"] == 0

    def test_enhance_deducts_cost(self, db, test_user):
        """각성 시 비용 차감"""
        initial_cash = test_user.cash
        cost = EnhanceConfig.get_cost(0)

        with patch("services.enhance_service.random.randint", return_value=1):
            result = EnhanceService.attempt_enhance(db, test_user.kakao_id)

        assert result["cost"] == cost
        assert result["cash"] == initial_cash - cost

    def test_enhance_fail_resets_to_zero(self, db, test_user):
        """실패 시 레벨 0으로 초기화"""
        test_user.enhance_level = 3
        db.commit()

        with patch(
            "services.enhance_service.random.randint", return_value=100
        ):  # 무조건 실패
            result = EnhanceService.attempt_enhance(db, test_user.kakao_id)

        assert result["success"] is True
        assert result["enhanced"] is False
        assert result["new_level"] == 0  # Lv.0으로 초기화
        assert result["drop"] == 3

    def test_enhance_fail_high_level_resets_to_zero(self, db, test_user):
        """고레벨에서 실패해도 Lv.0으로 초기화"""
        test_user.enhance_level = 8
        test_user.cash = 100_000_000
        db.commit()

        with patch(
            "services.enhance_service.random.randint", return_value=100
        ):  # 무조건 실패
            result = EnhanceService.attempt_enhance(db, test_user.kakao_id)

        assert result["enhanced"] is False
        assert result["new_level"] == 0  # Lv.0으로 초기화
        assert result["drop"] == 8

    def test_enhance_fail_clears_class(self, db, test_user):
        """실패로 Lv.0이 되면 계열도 풀린다.

        계열은 Lv.10 도달 시 배정되므로, 실패가 곧 다른 계열로 갈아탈
        기회가 된다. 계열이 남아 있으면 처음 뽑힌 계열에 영원히 묶인다.
        """
        test_user.enhance_level = 12
        test_user.enhance_class = 2
        test_user.cash = 100_000_000
        db.commit()

        with patch("services.enhance_service.random.randint", return_value=100):
            result = EnhanceService.attempt_enhance(db, test_user.kakao_id)

        assert result["enhanced"] is False
        assert result["new_level"] == 0
        db.refresh(test_user)
        assert test_user.enhance_class == 0, "실패했는데 계열이 그대로 남아 있다"

    def test_enhance_reassigns_class_after_reset(self, db, test_user):
        """계열이 풀린 뒤 다시 Lv.10에 도달하면 새로 배정된다"""
        test_user.enhance_level = EnhanceConfig.CLASS_LEVEL_THRESHOLD - 1
        test_user.enhance_class = 0
        test_user.cash = 100_000_000
        db.commit()

        with patch("services.enhance_service.random.randint", return_value=1):
            result = EnhanceService.attempt_enhance(db, test_user.kakao_id)

        assert result["enhanced"] is True
        assert result["new_level"] == EnhanceConfig.CLASS_LEVEL_THRESHOLD
        db.refresh(test_user)
        assert test_user.enhance_class != 0, "Lv.10에 도달했는데 계열이 안 붙었다"

    def test_enhance_fail_at_level_zero(self, db, test_user):
        """Lv.0에서 실패해도 Lv.0 유지"""
        test_user.enhance_level = 0
        db.commit()

        with patch(
            "services.enhance_service.random.randint", return_value=100
        ):  # 무조건 실패
            result = EnhanceService.attempt_enhance(db, test_user.kakao_id)

        assert result["enhanced"] is False
        assert result["new_level"] == 0
        assert result["drop"] == 0

    def test_enhance_max_level_blocked(self, db, test_user):
        """만렙에서는 각성 불가"""
        test_user.enhance_level = EnhanceConfig.MAX_LEVEL
        db.commit()

        result = EnhanceService.attempt_enhance(db, test_user.kakao_id)
        assert result["success"] is False

    def test_enhance_insufficient_cash(self, db, test_user):
        """잔고 부족 시 각성 불가"""
        test_user.cash = 0
        db.commit()

        result = EnhanceService.attempt_enhance(db, test_user.kakao_id)
        assert result["success"] is False

    def test_enhance_title_changes(self, db, test_user):
        """레벨업 시 칭호 변경 감지"""
        test_user.enhance_level = 3  # 시장 입문자 → 차트 분석가 경계
        test_user.cash = 100_000_000
        db.commit()

        with patch("services.enhance_service.random.randint", return_value=1):
            result = EnhanceService.attempt_enhance(db, test_user.kakao_id)

        assert result["enhanced"] is True
        assert result["new_level"] == 4
        assert result["title_changed"] is True
        valid_names = [t[0] for t in EnhanceConfig.TITLE_NAMES[4]]
        assert result["new_title"] in valid_names


class TestEnhanceConfig:
    """각성 설정 테스트"""

    def test_success_rates_length(self):
        """성공률 테이블이 MAX_LEVEL 개"""
        assert len(EnhanceConfig.SUCCESS_RATES) == EnhanceConfig.MAX_LEVEL

    def test_success_rates_decreasing(self):
        """성공률이 레벨이 올라갈수록 감소"""
        for i in range(1, len(EnhanceConfig.SUCCESS_RATES)):
            assert EnhanceConfig.SUCCESS_RATES[i] <= EnhanceConfig.SUCCESS_RATES[i - 1]

    def test_success_rates_positive(self):
        """모든 성공률이 양수"""
        for rate in EnhanceConfig.SUCCESS_RATES:
            assert rate > 0

    def test_max_level_is_actually_reachable(self):
        """만렙이 현실적으로 도달 가능해야 한다.

        실패하면 0으로 리셋되므로 Lv.N 도달 확률은 확률 N개의 곱이다.
        곱이라 개별 확률을 조금만 내려도 도달 확률이 무너진다. 예전 곡선은
        후반이 4~18%였는데, 그러면 Lv.20 도달이 128억분의 1(1초에 한 번씩
        눌러도 407년)이라 도감·칭호 같은 상위 콘텐츠가 통째로 사장된다.

        개별 확률만 보면 이 문제가 안 보이므로 곱으로 검증한다.
        """
        p = 1.0
        for rate in EnhanceConfig.SUCCESS_RATES:
            p *= rate / 100
        attempts = 1 / p
        assert attempts < 500, (
            f"만렙 도달에 기대 {attempts:,.0f}회 도전 필요 - 사실상 도달 불가"
        )

    def test_max_level_is_still_rare(self):
        """반대로 너무 쉬워도 안 된다. 만렙은 희소해야 의미가 있다."""
        p = 1.0
        for rate in EnhanceConfig.SUCCESS_RATES:
            p *= rate / 100
        assert p < 0.05, f"만렙 도달 확률 {p * 100:.1f}% - 너무 쉽다"

    def test_fail_resets_to_zero(self):
        """실패하면 현재 레벨 전부를 잃는다"""
        assert EnhanceConfig.get_fail_penalty(0) == (0, 0)
        assert EnhanceConfig.get_fail_penalty(7) == (100, 7)
        assert EnhanceConfig.get_fail_penalty(29) == (100, 29)

    def test_cost_is_affordable_from_daily_income(self):
        """한 번의 시도가 하루 고정 수입 안에서 감당돼야 한다.

        시도 비용이 하루 수입을 넘으면 각성 전용 재화를 따로 모으는
        게임이 되어버린다. 만렙 직전에도 하루 수입의 절반 아래여야 한다.
        """
        from game_config import GameConfig

        daily_floor = GameConfig.ATTENDANCE_REWARD + GameConfig.DAILY_MISSION_REWARD
        top_cost = EnhanceConfig.get_cost(EnhanceConfig.MAX_LEVEL - 1)
        assert top_cost < daily_floor * 0.5, (
            f"Lv.{EnhanceConfig.MAX_LEVEL - 1} 시도 비용 {top_cost:,}원이 "
            f"하루 고정 수입 {daily_floor:,}원에 비해 과하다"
        )

    def test_get_cost_increases(self):
        """레벨이 올라갈수록 비용 증가"""
        for i in range(EnhanceConfig.MAX_LEVEL - 1):
            assert EnhanceConfig.get_cost(i) < EnhanceConfig.get_cost(i + 1)

    def test_get_title_level_0(self):
        """레벨 0 칭호"""
        name, emoji = EnhanceConfig.get_title(0)
        valid_names = [t[0] for t in EnhanceConfig.TITLE_NAMES[0]]
        assert name in valid_names

    def test_get_title_max_level(self):
        """만렙 칭호"""
        name, emoji = EnhanceConfig.get_title(EnhanceConfig.MAX_LEVEL)
        valid_names = [t[0] for t in EnhanceConfig.TITLE_NAMES[EnhanceConfig.MAX_LEVEL]]
        assert name in valid_names
        assert emoji == "👑"

    def test_attendance_multiplier(self):
        """출석 보너스 배율 계산"""
        assert EnhanceConfig.get_attendance_multiplier(0) == 1.0
        assert EnhanceConfig.get_attendance_multiplier(10) == 1.5  # +50%
        assert EnhanceConfig.get_attendance_multiplier(20) == 2.0  # +100%

    def test_lottery_multiplier(self):
        """복권 보너스 배율 계산"""
        assert EnhanceConfig.get_lottery_multiplier(0) == 1.0
        assert EnhanceConfig.get_lottery_multiplier(10) == pytest.approx(1.8)  # +80%
        assert EnhanceConfig.get_lottery_multiplier(20) == pytest.approx(2.6)  # +160%

    def test_max_level_success_rate_zero(self):
        """만렙에서 성공률 0"""
        assert EnhanceConfig.get_success_rate(EnhanceConfig.MAX_LEVEL) == 0


class TestEnhanceWithAttendance:
    """각성 보너스가 출석에 적용되는지 테스트"""

    def test_attendance_with_enhance_bonus(self, db, test_user):
        """각성 레벨이 있으면 출석 보상 증가"""
        from services.user_service import UserService

        test_user.enhance_level = 10  # +50% 보너스
        db.commit()

        with (
            patch("services.asset_service.AssetService.record_daily_asset"),
            patch("services.user_service.log_attendance"),
        ):
            success, reward, streak, cash, enhance_level = UserService.check_attendance(
                db, test_user.kakao_id
            )

        assert success is True
        assert enhance_level == 10
        # 기본 30만 * 1.5 = 45만
        expected = int(
            GameConfig.ATTENDANCE_REWARD * EnhanceConfig.get_attendance_multiplier(10)
        )
        assert reward == expected


class TestEnhanceWithLottery:
    """각성 보너스가 복권에 적용되는지 테스트"""

    def test_lottery_with_enhance_bonus(self, db, test_user):
        """각성 레벨이 있으면 복권 보상 증가"""
        from services.game_service import GameService

        test_user.enhance_level = 5  # +40% 보너스
        db.commit()

        # 5등 (10000원) 고정
        with (
            patch("services.game_service.random.random", return_value=0.99),
            patch("services.game_service.random.randint", return_value=10000),
        ):
            result = GameService.play_lottery(db, test_user.kakao_id)

        assert result["success"] is True
        assert result["enhance_level"] == 5
        assert result["enhance_bonus"] > 0
