"""
데이터베이스 모델 정의
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, BigInteger, Integer, Float,
    DateTime, Date, ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from database import Base


def _utcnow():
    """timezone-aware UTC 현재 시각 (naive로 저장)"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    """유저 테이블"""
    __tablename__ = "users"
    
    # 카카오 유저 고유 ID
    kakao_id = Column(String(100), primary_key=True, index=True)
    
    # 닉네임 (카카오에서 제공되면 사용)
    nickname = Column(String(100), nullable=True)

    # 닉네임 변경 횟수 (초기 2회 + 한달마다 1회 추가)
    nickname_change_count = Column(Integer, default=0)
    last_nickname_change = Column(Date, nullable=True)
    
    # 보유 현금
    cash = Column(BigInteger, default=5_000_000)

    # 초기 자금 (수익률 계산용)
    initial_cash = Column(BigInteger, default=5_000_000)
    
    # 생성일
    created_at = Column(DateTime, default=_utcnow)
    
    # 출석 관련
    last_attendance = Column(Date, nullable=True)
    attendance_streak = Column(Integer, default=0)
    
    # 광고 관련
    last_ad_date = Column(Date, nullable=True)
    ad_count_today = Column(Integer, default=0)

    # 복권 관련 (1일 3회)
    last_lottery_date = Column(Date, nullable=True)
    lottery_count_today = Column(Integer, default=0)

    # 일간 미션 관련
    last_mission_date = Column(Date, nullable=True)
    daily_trade_count = Column(Integer, default=0)
    mission_completed = Column(Integer, default=0)  # 0: 미완료, 1: 완료

    # 업적 관련 (JSON 문자열로 저장)
    achievements = Column(String(1000), default="[]")
    total_profit_realized = Column(BigInteger, default=0)  # 실현 수익 누적
    total_trades = Column(Integer, default=0)  # 총 거래 횟수

    # 관계 설정
    holdings = relationship("Holding", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(kakao_id={self.kakao_id}, cash={self.cash:,})>"


class Holding(Base):
    """보유 주식 테이블"""
    __tablename__ = "holdings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 유저 ID
    kakao_id = Column(String(100), ForeignKey("users.kakao_id"), nullable=False, index=True)
    
    # 종목 정보
    stock_code = Column(String(20), nullable=False)  # 종목 코드
    stock_name = Column(String(100), nullable=False)  # 종목명
    
    # 보유 수량
    quantity = Column(Integer, default=0)
    
    # 평균 매수가
    avg_price = Column(Integer, default=0)
    
    # 총 매수 금액 (평균가 계산용)
    total_invested = Column(BigInteger, default=0)
    
    # 유니크 제약 + 복합 인덱스 (한 유저당 한 종목 하나의 레코드)
    __table_args__ = (
        UniqueConstraint('kakao_id', 'stock_code', name='unique_user_stock'),
        Index('ix_holding_user_stock', 'kakao_id', 'stock_code'),  # 조회 성능 최적화
    )
    
    # 관계 설정
    user = relationship("User", back_populates="holdings")
    
    def __repr__(self):
        return f"<Holding(user={self.kakao_id}, stock={self.stock_name}, qty={self.quantity})>"


class Transaction(Base):
    """거래 내역 테이블"""
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 유저 ID
    kakao_id = Column(String(100), ForeignKey("users.kakao_id"), nullable=False, index=True)
    
    # 종목 정보
    stock_code = Column(String(20), nullable=False)
    stock_name = Column(String(100), nullable=False)
    
    # 거래 유형 (BUY / SELL)
    trade_type = Column(String(10), nullable=False)
    
    # 거래 정보
    quantity = Column(Integer, nullable=False)  # 수량
    price = Column(Integer, nullable=False)  # 체결가
    total_amount = Column(BigInteger, nullable=False)  # 총 금액
    fee = Column(Integer, default=0)  # 수수료
    
    # 수익 (매도 시에만)
    profit = Column(BigInteger, nullable=True)
    profit_rate = Column(Float, nullable=True)
    
    # 거래 시간
    created_at = Column(DateTime, default=_utcnow)

    # 인덱스 (최근 거래 조회 최적화)
    __table_args__ = (
        Index('ix_transaction_user_created', 'kakao_id', 'created_at'),
    )

    # 관계 설정
    user = relationship("User", back_populates="transactions")

    def __repr__(self):
        return f"<Transaction({self.trade_type} {self.stock_name} {self.quantity}주 @ {self.price:,})>"


class Battle(Base):
    """배틀 테이블 - 2인 주가 예측 대결"""
    __tablename__ = "battles"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 도전자 (배틀 생성자)
    challenger_id = Column(String(100), ForeignKey("users.kakao_id"), nullable=False, index=True)

    # 상대방 (배틀 수락자)
    opponent_id = Column(String(100), ForeignKey("users.kakao_id"), nullable=True, index=True)

    # 배틀 대상 종목
    stock_code = Column(String(20), nullable=False)
    stock_name = Column(String(100), nullable=False)

    # 배틀 시작 시점 가격
    start_price = Column(Integer, nullable=True)

    # 투자 금액
    bet_amount = Column(BigInteger, default=100_000)

    # 예측 (UP / DOWN)
    challenger_prediction = Column(String(10), nullable=False)  # UP or DOWN
    opponent_prediction = Column(String(10), nullable=True)

    # 배틀 상태 (WAITING, ACTIVE, FINISHED, CANCELLED)
    status = Column(String(20), default="WAITING", index=True)

    # 최종 결과 가격
    end_price = Column(Integer, nullable=True)

    # 승자 kakao_id (무승부시 None)
    winner_id = Column(String(100), nullable=True)

    # 시간 정보
    created_at = Column(DateTime, default=_utcnow)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)

    # 배틀 지속 시간 (분)
    duration_minutes = Column(Integer, default=60)

    def __repr__(self):
        return f"<Battle(id={self.id}, {self.stock_name}, status={self.status})>"


class WeeklyChallenge(Base):
    """주간 챌린지 테이블"""
    __tablename__ = "weekly_challenges"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 챌린지 주차 (예: 2024-W01)
    week_id = Column(String(20), nullable=False, unique=True)

    # 챌린지 타입 (TRADE_COUNT, PROFIT_RATE, ASSET_GROWTH, STREAK 등)
    challenge_type = Column(String(50), nullable=False)

    # 챌린지 목표 값
    target_value = Column(Integer, nullable=False)

    # 챌린지 설명
    description = Column(String(500), nullable=False)

    # 보상 금액
    reward = Column(BigInteger, default=5_000_000)

    # 챌린지 시작/종료일
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)

    def __repr__(self):
        return f"<WeeklyChallenge({self.week_id}, {self.challenge_type})>"


class UserChallenge(Base):
    """유저별 챌린지 진행 현황"""
    __tablename__ = "user_challenges"

    id = Column(Integer, primary_key=True, autoincrement=True)

    kakao_id = Column(String(100), ForeignKey("users.kakao_id"), nullable=False, index=True)
    challenge_id = Column(Integer, ForeignKey("weekly_challenges.id"), nullable=False, index=True)

    # 현재 진행값
    current_value = Column(Integer, default=0)

    # 완료 여부
    completed = Column(Integer, default=0)  # 0: 미완료, 1: 완료

    # 보상 수령 여부
    reward_claimed = Column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint('kakao_id', 'challenge_id', name='unique_user_challenge'),
    )

    def __repr__(self):
        return f"<UserChallenge(user={self.kakao_id}, challenge={self.challenge_id})>"


class Milestone(Base):
    """마일스톤 달성 기록"""
    __tablename__ = "milestones"

    id = Column(Integer, primary_key=True, autoincrement=True)

    kakao_id = Column(String(100), ForeignKey("users.kakao_id"), nullable=False, index=True)

    # 마일스톤 타입 (ASSET_10M, ASSET_50M, ASSET_100M, TRADE_100, etc.)
    milestone_type = Column(String(50), nullable=False)

    # 달성 시점 자산
    asset_at_achievement = Column(BigInteger, nullable=True)

    # 달성 시간
    achieved_at = Column(DateTime, default=_utcnow)

    # 보상 지급 여부
    reward_claimed = Column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint('kakao_id', 'milestone_type', name='unique_user_milestone'),
    )

    def __repr__(self):
        return f"<Milestone(user={self.kakao_id}, type={self.milestone_type})>"


class AssetHistory(Base):
    """자산 히스토리 (차트용)"""
    __tablename__ = "asset_history"

    id = Column(Integer, primary_key=True, autoincrement=True)

    kakao_id = Column(String(100), ForeignKey("users.kakao_id"), nullable=False, index=True)

    # 기록 날짜
    record_date = Column(Date, nullable=False)

    # 해당 시점 총 자산
    total_asset = Column(BigInteger, nullable=False)

    # 현금
    cash = Column(BigInteger, nullable=False)

    # 주식 평가액
    stock_value = Column(BigInteger, default=0)

    __table_args__ = (
        UniqueConstraint('kakao_id', 'record_date', name='unique_user_date_asset'),
    )

    def __repr__(self):
        return f"<AssetHistory(user={self.kakao_id}, date={self.record_date}, asset={self.total_asset:,})>"


class StockCache(Base):
    """종목 코드/이름 영구 캐시"""
    __tablename__ = "stock_cache"

    # 종목 코드 (PK)
    stock_code = Column(String(20), primary_key=True)

    # 종목명
    stock_name = Column(String(100), nullable=False)

    # 마지막 업데이트
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    def __repr__(self):
        return f"<StockCache(code={self.stock_code}, name={self.stock_name})>"
