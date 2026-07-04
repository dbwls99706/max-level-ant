"""
유저 관리 서비스 (리팩토링)
- 회원가입
- 출석 체크
- 닉네임 검증 강화
- safe_add 적용
"""
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import exists

from models import User, ChatRoomMember
from config import GameConfig, EnhanceConfig, KST
from services.common import safe_add, safe_subtract, get_user_for_update
from utils import get_service_logger, log_attendance

logger = get_service_logger()


def register_chatroom_member(db: Session, group_key: str, kakao_id: str) -> None:
    """채팅방 멤버 등록/갱신 (그룹 챗봇용) - 별도 세션 사용하여 메인 세션 오염 방지"""
    if not group_key or not kakao_id:
        return
    from database import SessionLocal
    separate_db = None
    try:
        separate_db = SessionLocal()
        # FK 제약: users 테이블에 존재하는 유저만 등록 가능
        user_exists = separate_db.query(
            exists().where(User.kakao_id == kakao_id)
        ).scalar()
        if not user_exists:
            return

        existing = separate_db.query(ChatRoomMember).filter(
            ChatRoomMember.group_key == group_key,
            ChatRoomMember.kakao_id == kakao_id
        ).first()
        if existing:
            from models import _utcnow
            existing.last_active = _utcnow()
        else:
            member = ChatRoomMember(group_key=group_key, kakao_id=kakao_id)
            separate_db.add(member)
        separate_db.commit()
    except Exception:
        if separate_db:
            separate_db.rollback()
        logger.debug(f"채팅방 멤버 등록 실패: group={group_key[:8]}...")
    finally:
        if separate_db:
            separate_db.close()


class UserService:
    """유저 관련 비즈니스 로직"""

    # 닉네임 제한
    NICKNAME_MIN_LENGTH = 2
    NICKNAME_MAX_LENGTH = 12
    NICKNAME_PATTERN = re.compile(r'^[가-힣a-zA-Z0-9_]+$')

    # 금지 닉네임 패턴
    BANNED_PATTERNS = [
        r'admin', r'관리자', r'운영자', r'시스템', r'system',
        r'gm', r'운영', r'official', r'공식'
    ]

    @classmethod
    def validate_nickname(cls, nickname: str) -> Tuple[bool, str]:
        """
        닉네임 유효성 검증
        Returns: (is_valid, error_message)
        """
        if not nickname:
            return False, "닉네임을 입력해주세요."

        nickname = nickname.strip()

        # 길이 체크
        if len(nickname) < cls.NICKNAME_MIN_LENGTH:
            return False, f"닉네임은 최소 {cls.NICKNAME_MIN_LENGTH}자 이상이어야 합니다."

        if len(nickname) > cls.NICKNAME_MAX_LENGTH:
            return False, f"닉네임은 최대 {cls.NICKNAME_MAX_LENGTH}자까지 가능합니다."

        # 패턴 체크 (한글, 영문, 숫자, 언더스코어만 허용)
        if not cls.NICKNAME_PATTERN.match(nickname):
            return False, "닉네임은 한글, 영문, 숫자, 언더스코어(_)만 사용 가능합니다."

        # 금지 패턴 체크
        nickname_lower = nickname.lower()
        for pattern in cls.BANNED_PATTERNS:
            if re.search(pattern, nickname_lower):
                return False, "사용할 수 없는 닉네임입니다."

        # 공백만 있는 경우
        if not nickname.strip():
            return False, "닉네임을 입력해주세요."

        return True, ""

    @staticmethod
    def get_user(db: Session, kakao_id: str) -> Optional[User]:
        """유저 조회"""
        return db.query(User).filter(User.kakao_id == kakao_id).first()

    @classmethod
    def create_user(cls, db: Session, kakao_id: str, nickname: str = None) -> Tuple[User, bool]:
        """
        유저 생성 (기존 유저면 닉네임 업데이트)
        Returns: (User, is_new)
        """
        # 기존 유저 확인
        user = cls.get_user(db, kakao_id)
        if user:
            # 닉네임이 있으면 검증 후 업데이트
            if nickname and user.nickname != nickname:
                is_valid, _ = cls.validate_nickname(nickname)
                if is_valid:
                    try:
                        user.nickname = nickname
                        db.commit()
                        db.refresh(user)
                    except SQLAlchemyError as e:
                        db.rollback()
                        logger.error(f"닉네임 업데이트 DB 실패: {e}")
            return user, False

        # 닉네임 검증
        if nickname:
            is_valid, _ = cls.validate_nickname(nickname)
            if not is_valid:
                nickname = None  # 유효하지 않으면 None으로

        # 새 유저 생성
        try:
            user = User(
                kakao_id=kakao_id,
                nickname=nickname,
                cash=GameConfig.INITIAL_CASH,
                initial_cash=GameConfig.INITIAL_CASH,
                attendance_streak=0,
                ad_count_today=0
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"유저 생성 DB 실패: {e}")
            # 재시도: 동시 생성 가능성
            user = cls.get_user(db, kakao_id)
            if user:
                return user, False
            raise

        return user, True

    @classmethod
    def check_attendance(cls, db: Session, kakao_id: str) -> Tuple[bool, int, int, int, int]:
        """
        출석 체크 (FOR UPDATE로 동시성 제어)
        Returns: (success, reward, streak, current_cash, enhance_level)
        """
        # FOR UPDATE로 row lock 획득 (중복 출석 방지)
        user = get_user_for_update(db, kakao_id)
        if not user:
            return False, 0, 0, 0, 0

        today = datetime.now(KST).date()
        enhance_level = getattr(user, 'enhance_level', 0) or 0

        # 이미 출석했는지 확인
        if user.last_attendance == today:
            return False, 0, user.attendance_streak, user.cash, enhance_level

        # 연속 출석 계산
        yesterday = today - timedelta(days=1)
        if user.last_attendance == yesterday:
            user.attendance_streak += 1
        else:
            user.attendance_streak = 1

        # 보상 계산 (연속 출석 보너스)
        reward = GameConfig.ATTENDANCE_REWARD
        for days, multiplier in sorted(GameConfig.ATTENDANCE_STREAK_BONUS.items(), reverse=True):
            if user.attendance_streak >= days:
                reward = int(reward * multiplier)
                break

        # 각성 보너스 적용
        if enhance_level > 0:
            enhance_mult = EnhanceConfig.get_attendance_multiplier(enhance_level)
            reward = int(reward * enhance_mult)

        # 업데이트
        try:
            user.last_attendance = today
            user.cash = safe_add(user.cash, reward)
            db.commit()
            db.refresh(user)
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"출석 체크 DB 실패: {e}")
            return False, 0, 0, user.cash, enhance_level

        # 감사 로그
        log_attendance(
            kakao_id=kakao_id,
            reward=reward,
            streak=user.attendance_streak,
            cash_after=user.cash,
        )

        # 자산 히스토리 기록 (비동기적으로 - 실패해도 출석에는 영향 없음)
        try:
            from services.asset_service import AssetService
            AssetService.record_daily_asset(db, kakao_id)
        except Exception as e:
            db.rollback()  # 예외로 오염된 세션이 이후 커밋에 영향 주지 않도록
            logger.warning(f"자산 히스토리 기록 실패 (출석 후): {e}")

        # 출석 기반 보상 파이프라인 (스트릭 업적/마일스톤, 자산 마일스톤, 주간 챌린지)
        cls._run_attendance_rewards(db, kakao_id, user.attendance_streak)

        # 보상 지급으로 잔고가 바뀌었을 수 있으므로 최신값 반환
        db.refresh(user)

        return True, reward, user.attendance_streak, user.cash, enhance_level

    @classmethod
    def _run_attendance_rewards(cls, db: Session, kakao_id: str, streak: int) -> None:
        """
        출석 이벤트 기반 보상 체크 (실패해도 출석 자체에는 영향 없음)
        - 거래를 하지 않는 유저도 스트릭/자산 업적·마일스톤을 받을 수 있도록 출석에서 트리거
        """
        try:
            from services.asset_service import AssetService
            total_asset = AssetService.get_total_asset(db, kakao_id)
        except Exception as e:
            db.rollback()
            logger.warning(f"총 자산 계산 실패 (출석 후): {e}")
            total_asset = None

        try:
            from services.mission_service import MissionService
            from services.milestone_service import MilestoneService
            MissionService.check_and_award_achievements(db, kakao_id, total_asset=total_asset)
            MilestoneService.check_milestones(
                db, kakao_id,
                total_asset=total_asset,
                streak=streak,
            )
        except Exception as e:
            db.rollback()
            logger.warning(f"출석 업적/마일스톤 체크 실패 ({kakao_id}): {e}")

        try:
            from services.challenge_service import ChallengeService
            ChallengeService.update_challenge_progress(db, kakao_id, "ATTENDANCE")
            ChallengeService.update_asset_challenges(db, kakao_id, total_asset)
        except Exception as e:
            db.rollback()
            logger.warning(f"출석 챌린지 갱신 실패 ({kakao_id}): {e}")

    @staticmethod
    def get_balance(db: Session, kakao_id: str) -> Optional[int]:
        """잔고 조회"""
        user = UserService.get_user(db, kakao_id)
        if not user:
            return None
        return user.cash

    @staticmethod
    def update_cash(db: Session, kakao_id: str, amount: int) -> bool:
        """
        현금 업데이트 (FOR UPDATE로 동시성 제어)
        amount: 양수면 증가, 음수면 감소
        """
        # FOR UPDATE로 row lock 획득 (동시 수정 방지)
        user = get_user_for_update(db, kakao_id)
        if not user:
            return False

        if amount >= 0:
            new_cash = safe_add(user.cash, amount)
        else:
            # 잔액 부족 시 실패 (차감 전에 확인)
            if user.cash < abs(amount):
                return False
            new_cash = safe_subtract(user.cash, abs(amount))

        try:
            user.cash = new_cash
            db.commit()
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"현금 업데이트 DB 실패: {e}")
            return False

        return True

    @classmethod
    def is_nickname_taken(cls, db: Session, nickname: str, exclude_kakao_id: str = None) -> bool:
        """
        닉네임 중복 확인 (exists 쿼리로 최적화)
        exclude_kakao_id: 자기 자신은 제외 (닉네임 변경 시)
        """
        conditions = [User.nickname == nickname]
        if exclude_kakao_id:
            conditions.append(User.kakao_id != exclude_kakao_id)

        stmt = exists().where(*conditions)
        return db.query(stmt).scalar()

    @classmethod
    def update_nickname(cls, db: Session, kakao_id: str, new_nickname: str) -> Tuple[bool, str]:
        """
        닉네임 업데이트 (초기 2회 + 한달마다 1회 추가)
        Returns: (success, message)
        """
        user = cls.get_user(db, kakao_id)
        if not user:
            return False, "유저를 찾을 수 없습니다."

        # 닉네임 유효성 검증
        is_valid, err_msg = cls.validate_nickname(new_nickname)
        if not is_valid:
            return False, f"❌ {err_msg}"

        new_nickname = new_nickname.strip()

        # 현재 닉네임과 동일한 경우
        if user.nickname == new_nickname:
            return False, f"❌ 현재 닉네임과 동일합니다: {new_nickname}"

        # 닉네임 변경 가능 여부 확인
        change_count = getattr(user, 'nickname_change_count', 0) or 0
        last_change = getattr(user, 'last_nickname_change', None)
        today = datetime.now(KST).date()

        can_change = False
        remaining_msg = ""

        if change_count < 2:
            # 초기 2회 무료 변경
            can_change = True
            remaining = 2 - change_count - 1
            if remaining > 0:
                remaining_msg = f"남은 변경 횟수: {remaining}회"
            else:
                remaining_msg = "⚠️ 마지막 변경입니다! (한 달 후 1회 추가)"
        elif last_change:
            # 마지막 변경 후 30일 경과 시 1회 추가
            days_passed = (today - last_change).days
            if days_passed >= 30:
                can_change = True
                remaining_msg = "⚠️ 월간 변경권 사용 (다음 변경: 30일 후)"
            else:
                days_left = 30 - days_passed
                return False, f"❌ 닉네임 변경 횟수를 모두 사용했습니다.\n현재: {user.nickname}\n🕐 다음 변경 가능: {days_left}일 후"
        else:
            return False, f"❌ 닉네임 변경 횟수를 모두 사용했습니다.\n현재: {user.nickname}"

        if not can_change:
            return False, f"❌ 닉네임을 변경할 수 없습니다.\n현재: {user.nickname}"

        # 중복 확인
        if cls.is_nickname_taken(db, new_nickname, kakao_id):
            return False, f"❌ '{new_nickname}'은(는) 이미 사용 중인 닉네임입니다."

        try:
            user.nickname = new_nickname
            user.nickname_change_count = change_count + 1
            user.last_nickname_change = today
            db.commit()
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"닉네임 변경 DB 실패: {e}")
            return False, "❌ 닉네임 변경 중 오류가 발생했습니다."

        return True, f"✅ 닉네임이 '{new_nickname}'(으)로 설정되었습니다!\n{remaining_msg}"

    @classmethod
    def get_user_stats(cls, db: Session, kakao_id: str) -> Optional[Dict]:
        """유저 통계 조회"""
        user = cls.get_user(db, kakao_id)
        if not user:
            return None

        return {
            "kakao_id": kakao_id,
            "nickname": user.nickname or f"투자자{kakao_id[-4:]}",
            "cash": user.cash,
            "initial_cash": user.initial_cash,
            "total_trades": user.total_trades,
            "total_profit_realized": user.total_profit_realized or 0,
            "attendance_streak": user.attendance_streak,
            "created_at": str(user.created_at) if user.created_at else None
        }
