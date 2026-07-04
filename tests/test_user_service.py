"""
UserService 단위 테스트
- 유저 생성, 출석 체크, 닉네임 변경, 잔고 관리
"""

from datetime import timedelta
from unittest.mock import patch

from services.user_service import UserService
from config import GameConfig


class TestUserCreation:
    """유저 생성 테스트"""

    def test_create_new_user(self, db):
        """신규 유저 생성"""
        user, is_new = UserService.create_user(db, "new_kakao_id", "새유저")
        assert is_new is True
        assert user.kakao_id == "new_kakao_id"
        assert user.cash == GameConfig.INITIAL_CASH
        assert user.initial_cash == GameConfig.INITIAL_CASH

    def test_create_existing_user_returns_same(self, db, test_user):
        """기존 유저 재가입 시 동일 유저 반환"""
        user, is_new = UserService.create_user(db, test_user.kakao_id)
        assert is_new is False
        assert user.kakao_id == test_user.kakao_id

    def test_create_user_without_nickname(self, db):
        """닉네임 없이 유저 생성"""
        user, is_new = UserService.create_user(db, "no_nick_user")
        assert is_new is True
        assert user.nickname is None

    def test_create_user_invalid_nickname(self, db):
        """유효하지 않은 닉네임으로 유저 생성 - 닉네임 None으로 처리"""
        user, is_new = UserService.create_user(
            db, "bad_nick_user", "a" * 100
        )  # 너무 긴 닉네임
        assert is_new is True
        assert user.nickname is None


class TestNicknameValidation:
    """닉네임 유효성 검증 테스트"""

    def test_valid_nickname_korean(self):
        is_valid, _ = UserService.validate_nickname("주식왕")
        assert is_valid is True

    def test_valid_nickname_english(self):
        is_valid, _ = UserService.validate_nickname("StockKing")
        assert is_valid is True

    def test_valid_nickname_mixed(self):
        is_valid, _ = UserService.validate_nickname("주식king1")
        assert is_valid is True

    def test_invalid_nickname_too_short(self):
        is_valid, msg = UserService.validate_nickname("a")
        assert is_valid is False
        assert "이상" in msg

    def test_invalid_nickname_too_long(self):
        is_valid, msg = UserService.validate_nickname("a" * 20)
        assert is_valid is False
        assert "이하" in msg or "까지" in msg

    def test_invalid_nickname_special_chars(self):
        is_valid, _ = UserService.validate_nickname("test!@#")
        assert is_valid is False

    def test_invalid_nickname_admin(self):
        is_valid, _ = UserService.validate_nickname("admin123")
        assert is_valid is False

    def test_invalid_nickname_empty(self):
        is_valid, _ = UserService.validate_nickname("")
        assert is_valid is False

    def test_invalid_nickname_spaces_only(self):
        is_valid, _ = UserService.validate_nickname("   ")
        assert is_valid is False


class TestAttendance:
    """출석 체크 테스트"""

    def test_attendance_success(self, db, test_user):
        """출석 성공"""
        with (
            patch("services.asset_service.AssetService.record_daily_asset"),
            patch("services.user_service.log_attendance"),
        ):
            success, reward, streak, cash, _enhance = UserService.check_attendance(
                db, test_user.kakao_id
            )
        assert success is True
        assert reward >= GameConfig.ATTENDANCE_REWARD
        assert streak == 1
        assert cash > GameConfig.INITIAL_CASH

    def test_attendance_duplicate_same_day(self, db, test_user):
        """같은 날 두 번 출석 방지"""
        with (
            patch("services.asset_service.AssetService.record_daily_asset"),
            patch("services.user_service.log_attendance"),
        ):
            UserService.check_attendance(db, test_user.kakao_id)
            success, reward, streak, cash, _enhance = UserService.check_attendance(
                db, test_user.kakao_id
            )
        assert success is False
        assert reward == 0

    def test_attendance_unknown_user(self, db):
        """존재하지 않는 유저 출석"""
        success, reward, streak, cash, _enhance = UserService.check_attendance(
            db, "nonexistent_user"
        )
        assert success is False
        assert reward == 0

    def test_attendance_streak_continues(self, db, test_user):
        """연속 출석 스트릭 계산"""
        from config import KST
        from datetime import datetime

        # 어제 출석한 것으로 세팅
        yesterday = datetime.now(KST).date() - timedelta(days=1)
        test_user.last_attendance = yesterday
        test_user.attendance_streak = 3
        db.commit()

        with (
            patch("services.asset_service.AssetService.record_daily_asset"),
            patch("services.user_service.log_attendance"),
        ):
            success, reward, streak, cash, _enhance = UserService.check_attendance(
                db, test_user.kakao_id
            )

        assert success is True
        assert streak == 4  # 스트릭 증가

    def test_attendance_streak_reset(self, db, test_user):
        """연속 출석 스트릭 리셋 (2일 이상 빠짐)"""
        from datetime import datetime
        from config import KST

        # 3일 전 출석한 것으로 세팅
        old_date = datetime.now(KST).date() - timedelta(days=3)
        test_user.last_attendance = old_date
        test_user.attendance_streak = 10
        db.commit()

        with (
            patch("services.asset_service.AssetService.record_daily_asset"),
            patch("services.user_service.log_attendance"),
        ):
            success, reward, streak, cash, _enhance = UserService.check_attendance(
                db, test_user.kakao_id
            )

        assert success is True
        assert streak == 1  # 스트릭 리셋


class TestBalance:
    """잔고 관리 테스트"""

    def test_get_balance(self, db, test_user):
        balance = UserService.get_balance(db, test_user.kakao_id)
        assert balance == GameConfig.INITIAL_CASH

    def test_get_balance_nonexistent_user(self, db):
        balance = UserService.get_balance(db, "nobody")
        assert balance is None

    def test_update_cash_increase(self, db, test_user):
        result = UserService.update_cash(db, test_user.kakao_id, 1_000_000)
        assert result is True
        new_balance = UserService.get_balance(db, test_user.kakao_id)
        assert new_balance == GameConfig.INITIAL_CASH + 1_000_000

    def test_update_cash_decrease(self, db, test_user):
        result = UserService.update_cash(db, test_user.kakao_id, -1_000_000)
        assert result is True
        new_balance = UserService.get_balance(db, test_user.kakao_id)
        assert new_balance == GameConfig.INITIAL_CASH - 1_000_000

    def test_update_cash_insufficient(self, db, poor_user):
        """잔고 부족 시 실패"""
        result = UserService.update_cash(db, poor_user.kakao_id, -1_000_000)
        assert result is False


class TestNicknameChange:
    """닉네임 변경 테스트"""

    def test_change_nickname_first_time(self, db, test_user):
        """첫 번째 닉네임 변경"""
        success, msg = UserService.update_nickname(db, test_user.kakao_id, "새닉네임")
        assert success is True
        assert "새닉네임" in msg

        db.refresh(test_user)
        assert test_user.nickname == "새닉네임"
        assert test_user.nickname_change_count == 1

    def test_change_nickname_same_name(self, db, test_user):
        """현재 닉네임으로 변경 시도"""
        success, msg = UserService.update_nickname(
            db, test_user.kakao_id, test_user.nickname
        )
        assert success is False
        assert "동일" in msg

    def test_change_nickname_duplicate(self, db, test_user, rich_user):
        """중복 닉네임 변경 시도"""
        # rich_user 닉네임으로 변경 시도
        success, msg = UserService.update_nickname(
            db, test_user.kakao_id, rich_user.nickname
        )
        assert success is False
        assert "사용 중" in msg

    def test_change_nickname_exhausted(self, db, test_user):
        """닉네임 변경 횟수 소진"""
        from datetime import datetime
        from config import KST

        # 변경 횟수를 최대로 설정
        test_user.nickname_change_count = 2
        test_user.last_nickname_change = datetime.now(KST).date()  # 오늘 변경
        db.commit()

        success, msg = UserService.update_nickname(db, test_user.kakao_id, "또다른닉")
        assert success is False
        assert "사용했습니다" in msg
