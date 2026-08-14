"""
각성 시스템 (투자 감각 각성) 테스트
"""

import json
import pytest
from unittest.mock import patch

from enhance_art import CLASS_ART, RARITY_ART
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

    def test_enhance_fail_clears_job_and_rarity(self, db, test_user):
        """실패로 Lv.0이 되면 직군과 종이 풀린다.

        직군은 Lv.10 도달 시 배정되므로, 실패가 곧 다른 직군으로 갈아탈
        기회가 된다. 남아 있으면 처음 뽑힌 직군에 영원히 묶인다.
        """
        test_user.enhance_level = 12
        test_user.enhance_job = "scalper"
        test_user.enhance_rarity = "myth"
        test_user.cash = 100_000_000
        db.commit()

        with patch("services.enhance_service.random.randint", return_value=100):
            result = EnhanceService.attempt_enhance(db, test_user.kakao_id)

        assert result["enhanced"] is False
        assert result["new_level"] == 0
        db.refresh(test_user)
        assert test_user.enhance_job is None, "실패했는데 직군이 그대로 남아 있다"
        assert test_user.enhance_rarity is None, "실패했는데 종이 그대로 남아 있다"

    def test_enhance_fail_keeps_the_collection(self, db, test_user):
        """실패해도 도감 기록은 남는다. 판을 넘어 남는 유일한 자산이다."""
        from models import ClassCollection

        test_user.enhance_level = 12
        test_user.enhance_job = "scalper"
        test_user.enhance_rarity = "myth"
        test_user.cash = 100_000_000
        db.add(
            ClassCollection(
                kakao_id=test_user.kakao_id, job="scalper", rarity="myth", growth=2
            )
        )
        db.commit()

        with patch("services.enhance_service.random.randint", return_value=100):
            EnhanceService.attempt_enhance(db, test_user.kakao_id)

        kept = (
            db.query(ClassCollection)
            .filter(ClassCollection.kakao_id == test_user.kakao_id)
            .count()
        )
        assert kept == 1, "실패했다고 도감이 지워졌다"

    def test_enhance_assigns_job_after_reset(self, db, test_user):
        """직군이 풀린 뒤 다시 Lv.10에 도달하면 새로 배정된다"""
        test_user.enhance_level = EnhanceConfig.CLASS_LEVEL_THRESHOLD - 1
        test_user.enhance_job = None
        test_user.enhance_rarity = None
        test_user.cash = 100_000_000
        db.commit()

        with patch("services.enhance_service.random.randint", return_value=1):
            result = EnhanceService.attempt_enhance(db, test_user.kakao_id)

        assert result["enhanced"] is True
        assert result["new_level"] == EnhanceConfig.CLASS_LEVEL_THRESHOLD
        assert result["job_assigned"] is True
        db.refresh(test_user)
        assert test_user.enhance_job in CLASS_ART, "Lv.10인데 직군이 안 붙었다"
        assert test_user.enhance_rarity in RARITY_ART, "직군은 붙었는데 종이 없다"

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


class TestEnhanceFlavors:
    """레벨별 문구가 만렙까지 다 있고, 낡은 수치를 말하지 않는지"""

    def test_success_flavor_covers_every_level(self):
        """만렙까지 모든 레벨에 성공 문구가 있어야 한다.

        핸들러는 인덱스를 벗어나면 조용히 빈 문자열을 쓴다. 만렙을 20에서
        30으로 올렸을 때 Lv.21~30이 전부 문구 없이 나가는 걸 못 잡았다.
        """
        flavors = EnhanceConfig.SUCCESS_FLAVORS
        assert len(flavors) == EnhanceConfig.MAX_LEVEL + 1, (
            f"성공 문구 {len(flavors)}개 / 필요 {EnhanceConfig.MAX_LEVEL + 1}개"
        )
        empty = [lv for lv in range(1, EnhanceConfig.MAX_LEVEL + 1) if not flavors[lv]]
        assert not empty, f"문구가 빈 레벨: {empty}"

    def test_fail_flavor_covers_every_level(self):
        flavors = EnhanceConfig.FAIL_FLAVORS
        assert len(flavors) == EnhanceConfig.MAX_LEVEL, (
            f"실패 문구 {len(flavors)}개 / 필요 {EnhanceConfig.MAX_LEVEL}개"
        )
        assert all(flavors), "빈 실패 문구가 있다"

    def test_flavors_do_not_hardcode_probabilities(self):
        """문구에 확률 수치를 박으면 곡선을 고칠 때마다 거짓말이 된다.

        실제로 "4%를 뚫고 만렙 달성"이 확률 개편 뒤에도 그대로 남아 있었다.
        확률은 /각성 화면이 설정값에서 직접 읽어 보여준다.
        """
        import re

        offenders = [
            f
            for f in list(EnhanceConfig.SUCCESS_FLAVORS)
            + list(EnhanceConfig.FAIL_FLAVORS)
            if re.search(r"\d+\s*%", f)
        ]
        assert not offenders, f"확률이 박힌 문구: {offenders}"

    def test_title_table_covers_every_level(self):
        """칭호도 만렙까지 있어야 한다 (없으면 기본 칭호로 떨어진다)"""
        from enhance_config import DEFAULT_TITLE

        missing = [
            lv
            for lv in range(EnhanceConfig.MAX_LEVEL + 1)
            if EnhanceConfig.get_title(lv, seed=0) == DEFAULT_TITLE
            and lv not in EnhanceConfig.TITLE_NAMES
        ]
        assert not missing, f"칭호 없는 레벨: {missing}"


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


class TestMarketClosedMessage:
    """장 마감 안내 문구가 무엇이 막혔는지 정확히 말하는지"""

    def test_message_names_the_blocked_activity(self):
        """각성이 막혔는데 '예측 게임'이라고 하면 원인을 알 수 없다"""
        from unittest.mock import patch

        from services.common import check_market_closed_for_game

        with patch("services.common.is_market_open", return_value=True):
            _, err = check_market_closed_for_game("🧬", "각성")
        assert "각성" in err["message"]
        assert "예측 게임" not in err["message"]

    def test_enhance_handler_says_enhance(self, db, test_user):
        """핸들러 경로에서도 각성이라고 나와야 한다"""
        from unittest.mock import patch

        from handlers import CommandHandler

        with patch("services.common.is_market_open", return_value=True):
            handler = CommandHandler(db, test_user.kakao_id, "/각성 시도", "테스터", "")
            resp = handler.handle()

        text = json.dumps(resp, ensure_ascii=False)
        assert "각성" in text
        assert "예측 게임은" not in text


class TestMaxLevelMessaging:
    """만렙 축하 문구가 실제 만렙에서만 나오는지"""

    def _enhance_from(self, db, user, level):
        from handlers import CommandHandler

        user.enhance_level = level
        user.cash = 100_000_000
        db.commit()

        with (
            patch("services.common.is_market_open", return_value=False),
            patch("services.enhance_service.random.randint", return_value=1),
        ):
            handler = CommandHandler(db, user.kakao_id, "/각성 시도", "테스터", "")
            return json.dumps(handler.handle(), ensure_ascii=False)

    def test_below_max_does_not_claim_max_level(self, db, test_user):
        """만렙보다 낮은 레벨에서 '만렙 달성'이라고 하면 안 된다.

        구간 이펙트가 20으로 박혀 있어서, 만렙을 30으로 올린 뒤에도
        Lv.20에서 왕관과 함께 만렙 달성이라고 알렸다.
        """
        below = EnhanceConfig.MAX_LEVEL - 10
        text = self._enhance_from(db, test_user, below)
        assert f"Lv.{below + 1}" in text
        assert "만렙" not in text, f"Lv.{below + 1}인데 만렙이라고 한다"

    def test_reaching_max_level_celebrates(self, db, test_user):
        """진짜 만렙에서는 축하 문구가 나와야 한다"""
        text = self._enhance_from(db, test_user, EnhanceConfig.MAX_LEVEL - 1)
        assert "만렙" in text
