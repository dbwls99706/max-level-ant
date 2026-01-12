"""
유저 관리 서비스
- 회원가입
- 출석 체크
- 광고 보상
"""
from datetime import date, timedelta
from typing import Optional, Tuple
from sqlalchemy.orm import Session

from models import User
from config import GameConfig


class UserService:
    """유저 관련 비즈니스 로직"""
    
    @staticmethod
    def get_user(db: Session, kakao_id: str) -> Optional[User]:
        """유저 조회"""
        return db.query(User).filter(User.kakao_id == kakao_id).first()
    
    @staticmethod
    def create_user(db: Session, kakao_id: str, nickname: str = None) -> Tuple[User, bool]:
        """
        유저 생성 (기존 유저면 닉네임 업데이트)
        Returns: (User, is_new)
        """
        # 기존 유저 확인
        user = UserService.get_user(db, kakao_id)
        if user:
            # 닉네임이 있으면 업데이트
            if nickname and user.nickname != nickname:
                user.nickname = nickname
                db.commit()
                db.refresh(user)
            return user, False
        
        # 새 유저 생성
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
        
        return user, True
    
    @staticmethod
    def check_attendance(db: Session, kakao_id: str) -> Tuple[bool, int, int, int]:
        """
        출석 체크
        Returns: (success, reward, streak, current_cash)
        """
        user = UserService.get_user(db, kakao_id)
        if not user:
            return False, 0, 0, 0
        
        today = date.today()
        
        # 이미 출석했는지 확인
        if user.last_attendance == today:
            return False, 0, user.attendance_streak, user.cash
        
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
        
        # 업데이트
        user.last_attendance = today
        user.cash += reward
        
        db.commit()
        db.refresh(user)
        
        return True, reward, user.attendance_streak, user.cash

    # watch_ad() 제거됨 - 광고 기능 비활성화 (수익 발생 방지)

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
        현금 업데이트
        amount: 양수면 증가, 음수면 감소
        """
        user = UserService.get_user(db, kakao_id)
        if not user:
            return False

        new_cash = user.cash + amount
        if new_cash < 0:
            return False

        user.cash = new_cash
        db.commit()

        return True

    @staticmethod
    def is_nickname_taken(db: Session, nickname: str, exclude_kakao_id: str = None) -> bool:
        """
        닉네임 중복 확인
        exclude_kakao_id: 자기 자신은 제외 (닉네임 변경 시)
        """
        query = db.query(User).filter(User.nickname == nickname)

        if exclude_kakao_id:
            query = query.filter(User.kakao_id != exclude_kakao_id)

        return query.first() is not None

    @staticmethod
    def update_nickname(db: Session, kakao_id: str, new_nickname: str) -> Tuple[bool, str]:
        """
        닉네임 업데이트 (중복 검사 포함)
        Returns: (success, message)
        """
        user = UserService.get_user(db, kakao_id)
        if not user:
            return False, "유저를 찾을 수 없습니다."

        # 중복 확인
        if UserService.is_nickname_taken(db, new_nickname, kakao_id):
            return False, f"❌ '{new_nickname}'은(는) 이미 사용 중인 닉네임입니다."

        user.nickname = new_nickname
        db.commit()

        return True, f"✅ 닉네임이 '{new_nickname}'(으)로 설정되었습니다!"
