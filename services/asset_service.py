"""
자산 히스토리 서비스 - 포트폴리오 차트용
"""
from datetime import date, datetime, timedelta
from typing import Dict, List
from sqlalchemy.orm import Session

from models import AssetHistory, User, Holding
from services.stock_service import StockService


class AssetService:
    """자산 히스토리 관리"""

    @classmethod
    def record_daily_asset(cls, db: Session, kakao_id: str) -> Dict:
        """
        일일 자산 기록 (하루에 한 번)
        출석 체크나 거래 시 자동 호출
        """
        today = date.today()

        # 이미 오늘 기록이 있는지 확인
        existing = db.query(AssetHistory).filter(
            AssetHistory.kakao_id == kakao_id,
            AssetHistory.record_date == today
        ).first()

        if existing:
            return {"success": True, "message": "이미 기록됨", "updated": False}

        user = db.query(User).filter(User.kakao_id == kakao_id).first()
        if not user:
            return {"success": False, "message": "유저 없음"}

        # 총 자산 계산
        cash = user.cash
        stock_value = 0

        holdings = db.query(Holding).filter(Holding.kakao_id == kakao_id).all()
        for h in holdings:
            if h.quantity > 0:
                # 현재가 조회
                stock_info = StockService.get_stock_price(h.stock_code)
                if stock_info:
                    stock_value += stock_info["price"] * h.quantity
                else:
                    # 현재가 조회 실패 시 평균 매수가 사용
                    stock_value += h.avg_price * h.quantity

        total_asset = cash + stock_value

        # 기록 저장
        history = AssetHistory(
            kakao_id=kakao_id,
            record_date=today,
            total_asset=total_asset,
            cash=cash,
            stock_value=stock_value
        )
        db.add(history)
        db.commit()

        return {
            "success": True,
            "updated": True,
            "total_asset": total_asset,
            "cash": cash,
            "stock_value": stock_value
        }

    @classmethod
    def get_asset_history(cls, db: Session, kakao_id: str, days: int = 7) -> List[Dict]:
        """최근 N일간 자산 히스토리"""
        start_date = date.today() - timedelta(days=days)

        histories = db.query(AssetHistory).filter(
            AssetHistory.kakao_id == kakao_id,
            AssetHistory.record_date >= start_date
        ).order_by(AssetHistory.record_date).all()

        return [
            {
                "date": str(h.record_date),
                "total_asset": h.total_asset,
                "cash": h.cash,
                "stock_value": h.stock_value
            }
            for h in histories
        ]

    @classmethod
    def generate_ascii_chart(cls, db: Session, kakao_id: str, days: int = 7) -> str:
        """
        텍스트 기반 자산 차트 생성
        카카오톡은 이미지를 지원하지 않으므로 ASCII 차트 사용
        """
        history = cls.get_asset_history(db, kakao_id, days)

        if not history:
            return "📊 아직 자산 기록이 없습니다.\n내일 다시 확인해주세요!"

        if len(history) < 2:
            return f"📊 자산 기록 시작!\n현재 자산: {history[0]['total_asset']:,}원"

        # 최소/최대 자산
        assets = [h["total_asset"] for h in history]
        min_asset = min(assets)
        max_asset = max(assets)
        range_asset = max_asset - min_asset or 1

        # 차트 높이
        chart_height = 5
        chart_width = min(len(history), 7)

        # 차트 생성
        lines = []

        # 최대값 표시
        lines.append(f"📈 {max_asset:,}원")

        # 차트 바디
        for row in range(chart_height, 0, -1):
            line = ""
            threshold = min_asset + (range_asset * row / chart_height)

            for h in history[-chart_width:]:
                if h["total_asset"] >= threshold:
                    line += "█ "
                else:
                    line += "░ "

            lines.append(f"  {line}")

        # 최소값 표시
        lines.append(f"📉 {min_asset:,}원")

        # 날짜 표시 (간략하게)
        date_line = "   "
        for h in history[-chart_width:]:
            day = h["date"].split("-")[2]  # DD 부분만
            date_line += f"{day} "
        lines.append(date_line)

        # 변동률 계산
        first_asset = history[0]["total_asset"]
        last_asset = history[-1]["total_asset"]
        change = last_asset - first_asset
        change_rate = (change / first_asset) * 100 if first_asset > 0 else 0

        if change >= 0:
            change_emoji = "🔺"
        else:
            change_emoji = "🔻"

        lines.append(f"\n{change_emoji} {days}일 변동: {change:+,}원 ({change_rate:+.1f}%)")

        return "\n".join(lines)

    @classmethod
    def get_asset_summary(cls, db: Session, kakao_id: str) -> Dict:
        """자산 요약 정보"""
        history = cls.get_asset_history(db, kakao_id, 30)

        if not history:
            return {
                "has_history": False,
                "message": "아직 자산 기록이 없습니다."
            }

        current = history[-1]["total_asset"] if history else 0

        # 기간별 변동
        changes = {}

        if len(history) >= 2:
            changes["day"] = {
                "amount": current - history[-2]["total_asset"],
                "rate": ((current - history[-2]["total_asset"]) / history[-2]["total_asset"]) * 100 if history[-2]["total_asset"] > 0 else 0
            }

        if len(history) >= 7:
            week_ago = history[-7]["total_asset"]
            changes["week"] = {
                "amount": current - week_ago,
                "rate": ((current - week_ago) / week_ago) * 100 if week_ago > 0 else 0
            }

        if len(history) >= 30:
            month_ago = history[0]["total_asset"]
            changes["month"] = {
                "amount": current - month_ago,
                "rate": ((current - month_ago) / month_ago) * 100 if month_ago > 0 else 0
            }

        # 최고/최저
        all_time_high = max(h["total_asset"] for h in history)
        all_time_low = min(h["total_asset"] for h in history)

        return {
            "has_history": True,
            "current": current,
            "changes": changes,
            "all_time_high": all_time_high,
            "all_time_low": all_time_low,
            "record_count": len(history)
        }
