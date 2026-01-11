"""
랭킹 서비스
- 수익률 기준 랭킹
"""
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from cachetools import TTLCache

from models import User, Holding
from services.stock_service import StockService
from config import CacheConfig


class RankingService:
    """랭킹 관련 서비스"""
    
    # 랭킹 캐시
    _ranking_cache = TTLCache(maxsize=1, ttl=CacheConfig.RANKING_TTL)
    
    @classmethod
    def calculate_total_asset(cls, db: Session, user: User) -> Tuple[int, float]:
        """
        유저의 총 자산 및 수익률 계산
        Returns: (total_asset, profit_rate)
        """
        total_asset = user.cash
        
        # 보유 주식 가치 계산
        holdings = db.query(Holding).filter(
            Holding.kakao_id == user.kakao_id,
            Holding.quantity > 0
        ).all()
        
        for h in holdings:
            stock_info = StockService.get_price(h.stock_code)
            if stock_info:
                total_asset += stock_info["price"] * h.quantity
            else:
                # 시세 조회 실패 시 평균 매수가 사용
                total_asset += h.avg_price * h.quantity
        
        # 수익률 계산
        profit_rate = ((total_asset - user.initial_cash) / user.initial_cash) * 100
        
        return total_asset, profit_rate
    
    @classmethod
    def get_ranking(cls, db: Session, limit: int = 10) -> List[Dict]:
        """
        수익률 랭킹 TOP N
        """
        # 캐시 확인
        cache_key = f"ranking_{limit}"
        if cache_key in cls._ranking_cache:
            return cls._ranking_cache[cache_key]
        
        # 모든 유저 조회
        users = db.query(User).all()
        
        rankings = []
        for user in users:
            total_asset, profit_rate = cls.calculate_total_asset(db, user)
            rankings.append({
                "kakao_id": user.kakao_id,
                "nickname": user.nickname or f"용사{user.kakao_id[-4:]}",
                "total_asset": total_asset,
                "profit_rate": profit_rate
            })
        
        # 수익률 기준 정렬
        rankings.sort(key=lambda x: x["profit_rate"], reverse=True)
        
        # 순위 부여
        for i, r in enumerate(rankings):
            r["rank"] = i + 1
        
        result = rankings[:limit]
        
        # 캐시 저장
        cls._ranking_cache[cache_key] = result
        
        return result
    
    @classmethod
    def get_my_rank(cls, db: Session, kakao_id: str) -> Optional[Dict]:
        """
        내 순위 조회
        """
        user = db.query(User).filter(User.kakao_id == kakao_id).first()
        if not user:
            return None
        
        total_asset, profit_rate = cls.calculate_total_asset(db, user)
        
        # 전체 유저 수
        total_users = db.query(User).count()
        
        # 나보다 수익률 높은 유저 수
        all_users = db.query(User).all()
        higher_count = 0
        
        for u in all_users:
            if u.kakao_id == kakao_id:
                continue
            _, pr = cls.calculate_total_asset(db, u)
            if pr > profit_rate:
                higher_count += 1
        
        rank = higher_count + 1
        
        return {
            "rank": rank,
            "total": total_users,
            "kakao_id": kakao_id,
            "nickname": user.nickname or f"용사{kakao_id[-4:]}",
            "total_asset": total_asset,
            "profit_rate": profit_rate
        }
