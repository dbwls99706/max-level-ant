"""
데이터베이스 모델 정의
"""
from datetime import datetime, date
from sqlalchemy import (
    Column, String, BigInteger, Integer, Float,
    DateTime, Date, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship
from database import Base


class User(Base):
    """유저 테이블"""
    __tablename__ = "users"
    
    # 카카오 유저 고유 ID
    kakao_id = Column(String(100), primary_key=True, index=True)
    
    # 닉네임 (카카오에서 제공되면 사용)
    nickname = Column(String(100), nullable=True)
    
    # 보유 현금
    cash = Column(BigInteger, default=10_000_000)
    
    # 초기 자금 (수익률 계산용)
    initial_cash = Column(BigInteger, default=10_000_000)
    
    # 생성일
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 출석 관련
    last_attendance = Column(Date, nullable=True)
    attendance_streak = Column(Integer, default=0)
    
    # 광고 관련
    last_ad_date = Column(Date, nullable=True)
    ad_count_today = Column(Integer, default=0)

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
    kakao_id = Column(String(100), ForeignKey("users.kakao_id"), nullable=False)
    
    # 종목 정보
    stock_code = Column(String(20), nullable=False)  # 종목 코드
    stock_name = Column(String(100), nullable=False)  # 종목명
    
    # 보유 수량
    quantity = Column(Integer, default=0)
    
    # 평균 매수가
    avg_price = Column(Integer, default=0)
    
    # 총 매수 금액 (평균가 계산용)
    total_invested = Column(BigInteger, default=0)
    
    # 유니크 제약 (한 유저당 한 종목 하나의 레코드)
    __table_args__ = (
        UniqueConstraint('kakao_id', 'stock_code', name='unique_user_stock'),
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
    kakao_id = Column(String(100), ForeignKey("users.kakao_id"), nullable=False)
    
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
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 관계 설정
    user = relationship("User", back_populates="transactions")
    
    def __repr__(self):
        return f"<Transaction({self.trade_type} {self.stock_name} {self.quantity}주 @ {self.price:,})>"
