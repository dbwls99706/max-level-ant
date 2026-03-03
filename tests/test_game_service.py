"""
GameService 단위 테스트
- 복권, 시장예측(역사 퀴즈), 업다운(멀티라운드)
"""
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


class TestStockQuiz:
    """시장예측 (역사 퀴즈) 테스트"""

    def test_stock_quiz_success(self, db, rich_user):
        """역사 퀴즈 기본 실행"""
        with patch("services.common.is_market_open", return_value=False), \
             patch("services.game_service.log_game"):
            result = GameService.play_stock_quiz(db, rich_user.kakao_id, 10_000, "상승")
        assert result["success"] is True
        assert "quiz" in result
        assert "won" in result
        assert result["choice"] == "상승"

    def test_stock_quiz_invalid_choice(self, db, rich_user):
        """잘못된 선택"""
        with patch("services.common.is_market_open", return_value=False):
            result = GameService.play_stock_quiz(db, rich_user.kakao_id, 10_000, "급등")
        assert result["success"] is False
        assert result["error_code"] == ErrorCode.INVALID_CHOICE

    def test_stock_quiz_normalizes_choice(self, db, rich_user):
        """선택 정규화 (상 → 상승)"""
        with patch("services.common.is_market_open", return_value=False), \
             patch("services.game_service.log_game"):
            result = GameService.play_stock_quiz(db, rich_user.kakao_id, 10_000, "상")
        assert result["success"] is True
        assert result["choice"] == "상승"

    def test_stock_quiz_requires_market_closed(self, db, rich_user):
        """정규장 시간에 불가"""
        with patch("services.common.is_market_open", return_value=True), \
             patch("services.common.get_market_status_message", return_value="장 중"):
            result = GameService.play_stock_quiz(db, rich_user.kakao_id, 10_000, "상승")
        assert result["success"] is False
        assert result["error_code"] == ErrorCode.MARKET_CLOSED

    def test_stock_quiz_returns_quiz_data(self, db, rich_user):
        """퀴즈 데이터가 올바르게 반환되는지"""
        with patch("services.common.is_market_open", return_value=False), \
             patch("services.game_service.log_game"):
            result = GameService.play_stock_quiz(db, rich_user.kakao_id, 10_000, "상승")
        assert result["success"] is True
        quiz = result["quiz"]
        assert "stock_name" in quiz
        assert "period" in quiz
        assert "description" in quiz
        assert quiz["answer"] in ["상승", "하락"]


class TestUpdownMultiRound:
    """업다운 멀티라운드 테스트"""

    def test_start_updown(self, db, rich_user):
        """업다운 게임 시작"""
        with patch("services.common.is_market_open", return_value=False), \
             patch("services.game_service.log_game"):
            result = GameService.start_updown(db, rich_user.kakao_id, 50_000)
        assert result["success"] is True
        assert result["started"] is True
        assert 5 <= result["number"] <= 95
        assert result["round"] == 1
        assert result["multiplier"] == 1.0

    def test_start_updown_deducts_bet(self, db, rich_user):
        """게임 시작 시 투자금 차감"""
        initial_cash = rich_user.cash
        with patch("services.common.is_market_open", return_value=False), \
             patch("services.game_service.log_game"):
            result = GameService.start_updown(db, rich_user.kakao_id, 50_000)
        assert result["cash"] == initial_cash - 50_000

    def test_updown_round_win(self, db, rich_user):
        """업다운 라운드 적중"""
        with patch("services.common.is_market_open", return_value=False), \
             patch("services.game_service.log_game"):
            GameService.start_updown(db, rich_user.kakao_id, 50_000)

        # 현재 숫자를 강제 설정
        rich_user.updown_current_number = 30
        db.commit()

        # 다음 숫자를 60으로 고정 (상승 적중)
        with patch("services.game_service.random.choice", return_value=60), \
             patch("services.game_service.log_game"):
            result = GameService.play_updown_round(db, rich_user.kakao_id, "상승")
        assert result["success"] is True
        assert result["won"] is True
        assert result["total_multiplier"] > 1.0

    def test_updown_round_loss(self, db, rich_user):
        """업다운 라운드 실패"""
        with patch("services.common.is_market_open", return_value=False), \
             patch("services.game_service.log_game"):
            GameService.start_updown(db, rich_user.kakao_id, 50_000)

        rich_user.updown_current_number = 30
        db.commit()

        # 다음 숫자를 10으로 고정 (하락 → 상승 예측 실패)
        with patch("services.game_service.random.choice", return_value=10), \
             patch("services.game_service.log_game"):
            result = GameService.play_updown_round(db, rich_user.kakao_id, "상승")
        assert result["success"] is True
        assert result["won"] is False
        assert result["profit"] == -50_000

    def test_updown_cashout(self, db, rich_user):
        """업다운 중간 정산"""
        with patch("services.common.is_market_open", return_value=False), \
             patch("services.game_service.log_game"):
            GameService.start_updown(db, rich_user.kakao_id, 50_000)

        # 1라운드 적중 시뮬레이션
        rich_user.updown_current_number = 30
        rich_user.updown_round = 2
        rich_user.updown_multiplier = 1.42
        db.commit()

        with patch("services.game_service.log_game"):
            result = GameService.cashout_updown(db, rich_user.kakao_id)
        assert result["success"] is True
        assert result["multiplier"] == 1.42
        assert result["profit"] > 0

    def test_updown_cashout_requires_round(self, db, rich_user):
        """정산은 최소 1라운드 적중 필요"""
        with patch("services.common.is_market_open", return_value=False), \
             patch("services.game_service.log_game"):
            GameService.start_updown(db, rich_user.kakao_id, 50_000)

        result = GameService.cashout_updown(db, rich_user.kakao_id)
        assert result["success"] is False

    def test_updown_no_active_game(self, db, rich_user):
        """진행 중인 게임 없이 라운드 시도"""
        result = GameService.play_updown_round(db, rich_user.kakao_id, "상승")
        assert result["success"] is False
        assert result["error_code"] == ErrorCode.INVALID_STATE

    def test_updown_prevents_double_start(self, db, rich_user):
        """이미 진행 중인 게임이 있으면 새 게임 시작 불가"""
        with patch("services.common.is_market_open", return_value=False), \
             patch("services.game_service.log_game"):
            GameService.start_updown(db, rich_user.kakao_id, 50_000)
            result = GameService.start_updown(db, rich_user.kakao_id, 50_000)
        assert result["success"] is False
        assert result.get("active_game") is True

    def test_updown_invalid_choice(self, db, rich_user):
        """잘못된 선택"""
        with patch("services.common.is_market_open", return_value=False), \
             patch("services.game_service.log_game"):
            GameService.start_updown(db, rich_user.kakao_id, 50_000)

        result = GameService.play_updown_round(db, rich_user.kakao_id, "중간")
        assert result["success"] is False
        assert result["error_code"] == ErrorCode.INVALID_CHOICE
