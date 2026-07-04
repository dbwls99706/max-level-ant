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
    """시장예측 (역사 퀴즈) 테스트 — 출제/판정 2단계 (조작 방지)"""

    FIXED_QUIZ = {
        "stock_name": "삼성전자",
        "period": "2017년 1월 ~ 2018년 1월",
        "answer": "상승",
        "description": "반도체 슈퍼사이클로 메모리 수요 폭발",
    }

    def _play(self, db, kakao_id, bet, choice, quiz=None):
        """출제 → 판정 한 사이클 실행"""
        with patch("services.common.is_market_open", return_value=False), \
             patch("services.quiz_data_service.get_random_quiz",
                   return_value=quiz or self.FIXED_QUIZ), \
             patch("services.game_service.log_game"):
            issued = GameService.issue_stock_quiz(db, kakao_id, bet)
            assert issued["success"] is True
            return GameService.answer_stock_quiz(db, kakao_id, choice)

    def test_stock_quiz_success(self, db, rich_user):
        """역사 퀴즈 기본 실행 (출제 → 판정)"""
        result = self._play(db, rich_user.kakao_id, 10_000, "상승")
        assert result["success"] is True
        assert "quiz" in result
        assert "won" in result
        assert result["choice"] == "상승"

    def test_stock_quiz_correct_answer_wins(self, db, rich_user):
        """정답 선택 시 2배 지급"""
        initial_cash = rich_user.cash
        result = self._play(db, rich_user.kakao_id, 10_000, "상승")
        assert result["won"] is True
        assert result["cash"] == initial_cash + 10_000

    def test_stock_quiz_wrong_answer_loses(self, db, rich_user):
        """오답 선택 시 전액 손실"""
        initial_cash = rich_user.cash
        result = self._play(db, rich_user.kakao_id, 10_000, "하락")
        assert result["won"] is False
        assert result["cash"] == initial_cash - 10_000

    def test_stock_quiz_invalid_choice(self, db, rich_user):
        """잘못된 선택"""
        result = self._play(db, rich_user.kakao_id, 10_000, "급등")
        assert result["success"] is False
        assert result["error_code"] == ErrorCode.INVALID_CHOICE

    def test_stock_quiz_normalizes_choice(self, db, rich_user):
        """선택 정규화 (상 → 상승)"""
        result = self._play(db, rich_user.kakao_id, 10_000, "상")
        assert result["success"] is True
        assert result["choice"] == "상승"

    def test_stock_quiz_requires_market_closed(self, db, rich_user):
        """정규장 시간에 불가"""
        with patch("services.common.is_market_open", return_value=True), \
             patch("services.common.get_market_status_message", return_value="장 중"):
            result = GameService.issue_stock_quiz(db, rich_user.kakao_id, 10_000)
        assert result["success"] is False
        assert result["error_code"] == ErrorCode.MARKET_CLOSED

    def test_stock_quiz_answer_without_issue_fails(self, db, rich_user):
        """출제 없이 판정 시도 시 실패 (블라인드 배팅 차단)"""
        with patch("services.common.is_market_open", return_value=False):
            result = GameService.answer_stock_quiz(db, rich_user.kakao_id, "상승")
        assert result["success"] is False
        assert result["error_code"] == ErrorCode.INVALID_STATE

    def test_stock_quiz_reissue_returns_same_quiz(self, db, rich_user):
        """출제 후 재요청 시 같은 퀴즈 유지 (퀴즈 골라잡기 방지)"""
        other_quiz = {
            "stock_name": "카카오",
            "period": "2021년 6월 ~ 2022년 6월",
            "answer": "하락",
            "description": "규제 이슈",
        }
        with patch("services.common.is_market_open", return_value=False):
            with patch("services.quiz_data_service.get_random_quiz",
                       return_value=self.FIXED_QUIZ):
                first = GameService.issue_stock_quiz(db, rich_user.kakao_id, 10_000)
            with patch("services.quiz_data_service.get_random_quiz",
                       return_value=other_quiz):
                second = GameService.issue_stock_quiz(db, rich_user.kakao_id, 50_000)

        assert first["quiz"]["stock_name"] == second["quiz"]["stock_name"]
        assert second["reissued"] is True
        # 베팅 금액도 출제 시점 값으로 고정
        assert second["bet"] == 10_000

    def test_stock_quiz_pending_cleared_after_answer(self, db, rich_user):
        """판정 후 출제 상태 초기화 (1회용)"""
        self._play(db, rich_user.kakao_id, 10_000, "상승")
        db.refresh(rich_user)
        assert rich_user.pending_quiz is None
        assert rich_user.pending_quiz_bet == 0

        # 같은 퀴즈로 재판정 불가
        with patch("services.common.is_market_open", return_value=False):
            result = GameService.answer_stock_quiz(db, rich_user.kakao_id, "상승")
        assert result["success"] is False
        assert result["error_code"] == ErrorCode.INVALID_STATE

    def test_stock_quiz_returns_quiz_data(self, db, rich_user):
        """퀴즈 데이터가 올바르게 반환되는지"""
        result = self._play(db, rich_user.kakao_id, 10_000, "상승")
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
