"""
GameService 단위 테스트
- 복권, 슬롯, 룰렛, 하이로우, 동전
"""
import pytest
from unittest.mock import patch

from services.game_service import GameService
from config import GameConfig, ErrorCode


class TestLottery:
    """복권 테스트"""

    def test_lottery_success(self, db, test_user):
        """복권 기본 실행"""
        with patch("services.game_service.log_game"):
            result = GameService.play_lottery(db, test_user.kakao_id)
        assert result["success"] is True
        assert "tier" in result
        assert "reward" in result
        assert "cash" in result

    def test_lottery_is_free(self, db, test_user):
        """복권은 무료 (비용 차감 없음)"""
        initial_cash = test_user.cash
        with patch("services.game_service.log_game"):
            result = GameService.play_lottery(db, test_user.kakao_id)
        # 무료이므로 잔고는 항상 초기값 이상 (당첨금만 추가)
        assert result["cash"] >= initial_cash

    def test_lottery_daily_limit(self, db, test_user):
        """복권 일일 제한"""
        with patch("services.game_service.log_game"):
            for _ in range(GameConfig.MAX_LOTTERY_PER_DAY):
                result = GameService.play_lottery(db, test_user.kakao_id)
                assert result["success"] is True

            result = GameService.play_lottery(db, test_user.kakao_id)

        assert result["success"] is False
        assert result["error_code"] == ErrorCode.DAILY_LIMIT_REACHED

    def test_lottery_free_for_poor_user(self, db, poor_user):
        """잔고 없어도 복권 가능 (무료)"""
        with patch("services.game_service.log_game"):
            result = GameService.play_lottery(db, poor_user.kakao_id)
        assert result["success"] is True


class TestSlotMachine:
    """슬롯머신 테스트"""

    def test_slot_requires_market_closed(self, db, test_user):
        """슬롯은 정규장 시간에 불가"""
        # check_market_closed_for_game이 services.common.is_market_open를 사용
        with patch("services.common.is_market_open", return_value=True), \
             patch("services.common.get_market_status_message", return_value="장 중"):
            result = GameService.play_slot(db, test_user.kakao_id, 50_000)
        assert result["success"] is False
        assert result["error_code"] == ErrorCode.MARKET_CLOSED

    def test_slot_success(self, db, test_user):
        """슬롯 기본 실행"""
        with patch("services.common.is_market_open", return_value=False), \
             patch("services.game_service.log_game"):
            result = GameService.play_slot(db, test_user.kakao_id, 50_000)
        assert result["success"] is True
        assert "slots" in result
        assert len(result["slots"]) == 3

    def test_slot_invalid_bet(self, db, test_user):
        """유효하지 않은 배팅금"""
        with patch("services.common.is_market_open", return_value=False):
            result = GameService.play_slot(db, test_user.kakao_id, -100)
        assert result["success"] is False


class TestRoulette:
    """룰렛 테스트"""

    def test_roulette_win_red(self, db, rich_user):
        """빨강 당첨"""
        import random
        with patch("services.common.is_market_open", return_value=False), \
             patch("services.game_service.log_game"), \
             patch("random.random", return_value=0.01):  # 빨강 당첨 확률 범위
            result = GameService.play_roulette(db, rich_user.kakao_id, 10_000, "빨강")
        assert result["success"] is True

    def test_roulette_invalid_choice(self, db, rich_user):
        """잘못된 선택"""
        with patch("services.common.is_market_open", return_value=False):
            result = GameService.play_roulette(db, rich_user.kakao_id, 10_000, "노랑")
        assert result["success"] is False
        assert result["error_code"] == ErrorCode.INVALID_CHOICE

    def test_roulette_normalizes_choice(self, db, rich_user):
        """선택 정규화 (빨 → 빨강)"""
        with patch("services.common.is_market_open", return_value=False), \
             patch("services.game_service.log_game"):
            result = GameService.play_roulette(db, rich_user.kakao_id, 10_000, "빨")
        assert result["success"] is True


class TestHighLow:
    """하이로우 테스트"""

    def test_highlow_win(self, db, rich_user):
        """하이로우 당첨"""
        with patch("services.common.is_market_open", return_value=False), \
             patch("services.game_service.log_game"), \
             patch("random.randint", return_value=75):  # 높음
            result = GameService.play_high_low(db, rich_user.kakao_id, 10_000, "높")
        assert result["success"] is True
        assert result["won"] is True

    def test_highlow_draw(self, db, rich_user):
        """하이로우 무승부 (50)"""
        with patch("services.common.is_market_open", return_value=False), \
             patch("random.randint", return_value=50):
            result = GameService.play_high_low(db, rich_user.kakao_id, 10_000, "높")
        assert result["success"] is True
        assert result["won"] is None  # 무승부
        assert result["profit"] == 0

    def test_highlow_invalid_choice(self, db, rich_user):
        """잘못된 선택"""
        with patch("services.common.is_market_open", return_value=False):
            result = GameService.play_high_low(db, rich_user.kakao_id, 10_000, "중간")
        assert result["success"] is False
        assert result["error_code"] == ErrorCode.INVALID_CHOICE


class TestCoinFlip:
    """동전 던지기 테스트"""

    def test_coinflip_win(self, db, rich_user):
        """동전 당첨"""
        with patch("services.common.is_market_open", return_value=False), \
             patch("services.game_service.log_game"), \
             patch("random.choice", return_value="앞"):
            result = GameService.play_coin_flip(db, rich_user.kakao_id, 10_000, "앞")
        assert result["success"] is True
        assert result["won"] is True

    def test_coinflip_loss(self, db, rich_user):
        """동전 패배"""
        with patch("services.common.is_market_open", return_value=False), \
             patch("services.game_service.log_game"), \
             patch("random.choice", return_value="뒤"):
            result = GameService.play_coin_flip(db, rich_user.kakao_id, 10_000, "앞")
        assert result["success"] is True
        assert result["won"] is False
        assert result["winnings"] == 0
        assert result["profit"] < 0
