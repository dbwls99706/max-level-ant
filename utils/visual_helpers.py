"""
시각적 도파민 강화 유틸리티
- 스트릭 불꽃 시각화
- 수익률 게이지 바
- 등급별 이모지
"""
import re


def get_streak_display(streak: int) -> str:
    """
    연속 출석 스트릭을 시각적으로 표현

    1-2일: 🔥
    3-4일: 🔥🔥
    5-6일: 🔥🔥🔥
    7일+: 🔥🔥🔥 ⭐ (특별함 표현)
    14일+: 💎🔥🔥🔥🔥
    """
    if streak <= 0:
        return ""
    elif streak < 3:
        return "🔥"
    elif streak < 5:
        return "🔥🔥"
    elif streak < 7:
        return "🔥🔥🔥"
    elif streak < 14:
        return "🔥🔥🔥 ⭐"
    elif streak < 30:
        return "💎🔥🔥🔥🔥"
    else:
        return "👑💎🔥🔥🔥🔥🔥"


def get_profit_bar(profit_rate: float, width: int = 10) -> str:
    """
    수익률을 게이지 바로 표현

    예: ▓▓▓▓░░░░░░ (+23.5%)
    """
    # 수익률 절대값 기준으로 바 길이 결정 (10%당 1칸)
    filled = int(abs(profit_rate) / 10)
    filled = min(filled, width)

    bar = "▓" * filled + "░" * (width - filled)

    if profit_rate >= 0:
        return f"📈 {bar} ({profit_rate:+.1f}%)"
    else:
        return f"📉 {bar} ({profit_rate:+.1f}%)"


def get_rank_emoji(rank: int) -> str:
    """순위별 이모지 (일관된 형식)"""
    if rank == 1:
        return "🥇"
    elif rank == 2:
        return "🥈"
    elif rank == 3:
        return "🥉"
    else:
        return f"{rank}위"


def get_profit_emoji(profit_rate: float) -> str:
    """수익률별 이모지"""
    if profit_rate >= 100:
        return "🚀💰"  # 100% 이상 대박
    elif profit_rate >= 50:
        return "🚀"    # 50% 이상
    elif profit_rate >= 20:
        return "📈"    # 20% 이상
    elif profit_rate >= 0:
        return "💹"    # 양수
    elif profit_rate >= -20:
        return "📉"    # -20% 이상
    elif profit_rate >= -50:
        return "💔"    # -50% 이상
    else:
        return "🆘"    # -50% 미만


def get_tier_title(total_asset: int) -> str:
    """
    총 자산 기준 등급 타이틀
    """
    if total_asset >= 1_000_000_000:  # 10억
        return "💎 전설의 투자자"
    elif total_asset >= 500_000_000:  # 5억
        return "👑 투자의 신"
    elif total_asset >= 100_000_000:  # 1억
        return "🏆 자산가"
    elif total_asset >= 50_000_000:   # 5천만
        return "⭐ 재테크 고수"
    elif total_asset >= 20_000_000:   # 2천만
        return "📊 중급 투자자"
    elif total_asset >= 10_000_000:   # 1천만
        return "🌱 초보 투자자"
    else:
        return "😢 파산 위기"


def sanitize_input(text: str, max_length: int = 100) -> str:
    """
    사용자 입력 정제 (XSS 방지)
    """
    if not text:
        return ""

    # 길이 제한
    text = text[:max_length]

    # 위험한 문자 제거/이스케이프
    # 중요: & 문자를 먼저 치환해야 다른 문자들이 &lt; 등으로 변환된 후
    # &가 다시 &amp;lt;로 바뀌는 것을 방지
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    text = text.replace('"', '&quot;')
    text = text.replace("'", '&#39;')

    return text.strip()


def format_money(amount: int) -> str:
    """
    금액을 한국어 단위로 표시
    예: 1억 2,345만원
    """
    if amount >= 100_000_000:
        억 = amount // 100_000_000
        나머지 = (amount % 100_000_000) // 10_000
        if 나머지 > 0:
            return f"{억}억 {나머지:,}만원"
        return f"{억}억원"
    elif amount >= 10_000:
        만 = amount // 10_000
        return f"{만:,}만원"
    else:
        return f"{amount:,}원"
