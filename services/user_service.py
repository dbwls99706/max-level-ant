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
        유저 생성
        Returns: (User, is_new)
        """
        # 기존 유저 확인
        user = UserService.get_user(db, kakao_id)
        if user:
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
    
    @staticmethod
    def watch_ad(db: Session, kakao_id: str) -> Tuple[bool, int, int, int]:
        """
        광고 시청 보상
        Returns: (success, reward, remaining_count, current_cash)
        """
        user = UserService.get_user(db, kakao_id)
        if not user:
            return False, 0, 0, 0
        
        today = date.today()
        
        # 날짜가 바뀌었으면 카운트 리셋
        if user.last_ad_date != today:
            user.last_ad_date = today
            user.ad_count_today = 0
        
        # 최대 횟수 확인
        if user.ad_count_today >= GameConfig.MAX_ADS_PER_DAY:
            remaining = 0
            return False, 0, remaining, user.cash
        
        # 보상 지급
        reward = GameConfig.AD_REWARD
        user.ad_count_today += 1
        user.cash += reward
        
        remaining = GameConfig.MAX_ADS_PER_DAY - user.ad_count_today
        
        db.commit()
        db.refresh(user)
        
        return True, reward, remaining, user.cash
    
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
