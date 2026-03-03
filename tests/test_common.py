"""
services/common.py 단위 테스트
- safe_add, safe_subtract, safe_multiply
- validate_bet, validate_quantity
- error_response, success_response
"""
import pytest
from services.common import (
    safe_add, safe_subtract, safe_multiply,
    validate_bet, validate_quantity,
    error_response, success_response,
    MAX_SAFE_AMOUNT,
)
from config import GameConfig


class TestSafeMath:
    """안전 수학 연산 테스트"""

    def test_safe_add_normal(self):
        assert safe_add(100, 200) == 300

    def test_safe_add_cap(self):
        """최대값 초과 시 cap"""
        result = safe_add(MAX_SAFE_AMOUNT, 1)
        assert result == MAX_SAFE_AMOUNT

    def test_safe_add_zero(self):
        assert safe_add(0, 0) == 0

    def test_safe_subtract_normal(self):
        assert safe_subtract(500, 200) == 300

    def test_safe_subtract_below_zero(self):
        """음수 방지"""
        result = safe_subtract(100, 500)
        assert result == 0

    def test_safe_subtract_exact_zero(self):
        assert safe_subtract(100, 100) == 0

    def test_safe_multiply_normal(self):
        assert safe_multiply(100, 2.0) == 200

    def test_safe_multiply_cap(self):
        """최대값 초과 시 cap"""
        result = safe_multiply(MAX_SAFE_AMOUNT, 2.0)
        assert result == MAX_SAFE_AMOUNT

    def test_safe_multiply_fraction(self):
        assert safe_multiply(100, 1.5) == 150

    def test_safe_multiply_zero_multiplier(self):
        assert safe_multiply(1_000_000, 0) == 0


class TestValidateBet:
    """투자금 검증 테스트"""

    def test_valid_bet(self):
        is_valid, _ = validate_bet(10_000, 1_000_000)
        assert is_valid is True

    def test_bet_too_small(self):
        is_valid, msg = validate_bet(0, 1_000_000)
        assert is_valid is False
        assert "0보다" in msg

    def test_bet_exceeds_cash(self):
        is_valid, msg = validate_bet(1_000_000, 500_000)
        assert is_valid is False
        assert "잔액 부족" in msg

    def test_bet_below_min(self):
        is_valid, msg = validate_bet(100, 1_000_000, min_bet=10_000)
        assert is_valid is False
        assert "최소" in msg

    def test_bet_above_max(self):
        is_valid, msg = validate_bet(200_000, 1_000_000, max_bet=100_000)
        assert is_valid is False
        assert "최대" in msg

    def test_bet_exactly_cash(self):
        """잔액과 동일한 투자금 허용"""
        is_valid, _ = validate_bet(500_000, 500_000)
        assert is_valid is True


class TestValidateQuantity:
    """수량 검증 테스트"""

    def test_valid_quantity(self):
        is_valid, _ = validate_quantity(10)
        assert is_valid is True

    def test_quantity_zero(self):
        is_valid, msg = validate_quantity(0)
        assert is_valid is False
        assert "0보다" in msg

    def test_quantity_negative(self):
        is_valid, msg = validate_quantity(-5)
        assert is_valid is False

    def test_quantity_exceeds_max(self):
        is_valid, msg = validate_quantity(GameConfig.MAX_QUANTITY + 1)
        assert is_valid is False
        assert "최대" in msg


class TestResponseBuilders:
    """응답 빌더 테스트"""

    def test_error_response_basic(self):
        resp = error_response("ERR_001", "오류 발생")
        assert resp["success"] is False
        assert resp["error_code"] == "ERR_001"
        assert resp["message"] == "오류 발생"

    def test_error_response_with_data(self):
        resp = error_response("ERR_001", "오류", data={"key": "value"})
        assert resp["data"] == {"key": "value"}

    def test_success_response_basic(self):
        resp = success_response("성공")
        assert resp["success"] is True
        assert resp["message"] == "성공"

    def test_success_response_with_data(self):
        resp = success_response("성공", cash=5_000_000)
        assert resp["cash"] == 5_000_000
