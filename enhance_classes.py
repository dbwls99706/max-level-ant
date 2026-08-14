"""
각성 직군/종/성장 - 게임 쪽 데이터

`enhance_art`가 이미지 생성용 데이터라면, 이 모듈은 그 이미지를 게임에서
쓰기 위한 데이터다. 직군 이름·이모지 같은 공통 정보는 여기 다시 적지 않고
`enhance_art`에서 가져온다. 두 곳에 적으면 한쪽만 바뀌었을 때
이미지와 문구가 다른 직군을 가리키게 된다.

이미지 한 장은 (직군, 종, 성장) 조합 하나다. 각성 성공 문구도 같은 세 축으로
조립해서, 유저가 받은 그림과 읽는 문장이 항상 같은 것을 가리키게 한다.
600개를 손으로 쓰면 톤이 흔들리고 직군을 추가할 때마다 15줄씩 늘어난다.

순수 데이터와 조회 함수만 담는다. DB·핸들러는 건드리지 않는다.
"""

from typing import Dict, List, Optional, Tuple

from enhance_art import (
    CLASS_ART,
    FAMILIES,
    NOVICE_ART,
    RARITY_ART,
    image_stem,
    novice_stem,
)

# ===========================================
# 성장 단계 - 레벨에서 파생된다
# ===========================================
# 종은 뽑기 운이지만 성장은 노력이다. 레벨을 올리면 종이 낮아도
# 그림이 확실히 달라지는 축이므로, 그림이 붙는 레벨 구간을 6등분해서 매핑한다.
GROWTH_STAGES: Dict[int, str] = {
    1: "각성",
    2: "발현",
    3: "숙련",
    4: "정예",
    5: "극한",
    6: "초월",
}


def growth_stage(level: int, max_level: int, first_level: int = 1) -> int:
    """레벨 -> 성장 단계(1~6).

    first_level은 '이 그림이 붙기 시작하는 레벨'이다. 직군 그림은 직군을
    받는 Lv.10부터 붙으므로 10..30을 6등분해야 한다. 1..30을 6등분하면
    앞의 두 단계가 직군 없는 구간에 배정돼 그림이 통째로 사장된다 -
    실제로 예전 3단계 시절 1단계 200장이 Lv.10 한 레벨에만 쓰였다.

    쪼렙 구간(직군 없음)처럼 다른 범위를 쓰는 그림은 first_level을 바꿔 부른다.
    """
    stages = len(GROWTH_STAGES)
    span = max(1, max_level - first_level + 1)
    if level <= first_level:
        return 1
    # 나눗셈을 실수로 두는 이유: 21레벨을 6단계로 나누면 3.5레벨씩이라
    # 정수로 자르면 마지막 단계가 한 레벨만 갖는 쏠림이 생긴다.
    stage = int((level - first_level) / (span / stages)) + 1
    return max(1, min(stage, stages))


# ===========================================
# 종(희귀도) - 확률과 수익률 보정
# ===========================================
# 확률은 노멀이 가장 두껍고 신화로 갈수록 급격히 얇아진다.
# 보정 상한은 10%다. 이보다 크면 종 하나가 매매 실력을 덮어버린다.
#
#   key: (뽑힐 확률, 수익률 보정 %)
RARITY_ODDS: Dict[str, Tuple[float, float]] = {
    "normal": (0.50, 0.0),
    "rare": (0.28, 2.0),
    "epic": (0.15, 4.0),
    "legend": (0.06, 7.0),
    "myth": (0.01, 10.0),
}

# 종을 다시 뽑을 수 있는 레벨. 이 지점을 넘길 때마다 한 번씩 기회가 온다.
RARITY_REROLL_LEVELS = (10, 20, 30)


def rarity_bonus(rarity: str) -> float:
    """종에 따른 수익률 보정 (%)"""
    return RARITY_ODDS.get(rarity, (0.0, 0.0))[1]


def rarity_label(rarity: str) -> str:
    """도감·랭킹에 쓸 표기 (예: '🟨 신화')"""
    name, emoji, _fx = RARITY_ART[rarity]
    return f"{emoji} {name}"


# ===========================================
# 각성 문구 - 세 축으로 조립한다
# ===========================================
# 종: 뽑은 순간의 온도. 문장 맨 앞에 온다.
RARITY_FLAVORS: Dict[str, str] = {
    "normal": "평범한 빛이 스며듭니다.",
    "rare": "푸른 기운이 윤곽을 따라 흐릅니다.",
    "epic": "보랏빛 파편이 주위를 맴돕니다.",
    "legend": "부서진 빛이 공중에 멈춰 섭니다.",
    "myth": "황금빛이 휘어지며 세상이 잠시 숨을 멈춥니다.",
}

# 성장: 지금 어떤 모습인지. 문장 맨 뒤에 온다.
GROWTH_FLAVORS: Dict[int, str] = {
    1: "아직 맨몸이지만, 손에 쥔 것만은 분명합니다.",
    2: "가죽 흉갑 하나가 늘었습니다. 첫 흠집도 함께 늘었습니다.",
    3: "긁힌 갑옷과 짧은 망토. 몇 번은 넘어져 본 자의 것입니다.",
    4: "양어깨가 맞춰졌습니다. 이제 서 있는 자리가 흔들리지 않습니다.",
    5: "투구의 볏이 서고 망토가 깃발처럼 늘어집니다. 한 걸음 남았습니다.",
    6: "전신을 덮은 판금에 금빛이 흐릅니다. 더 오를 곳이 없습니다.",
}

# 직군: 각성하는 그 장면. 이미지의 무기·소품과 같은 것을 가리킨다.
CLASS_FLAVORS: Dict[str, str] = {
    # ── ⚡ 트레이더 ──
    "scalper": "가느다란 캔들 심지가 칼날이 되어 손에 잡힙니다.",
    "swinger": "발밑의 파도가 굳어 보드가 됩니다. 이제 골짜기가 보입니다.",
    "momentum": "시위가 팽팽히 당겨집니다. 화살은 위만 봅니다.",
    "contrarian": "떨어지는 붉은 칼날을 맨손으로 붙잡았습니다.",
    "orderflow": "바닥에 찍힌 호가의 발자국이 하나씩 빛나기 시작합니다.",
    # ── 📜 투자가 ──
    "valuehunter": "돌덩이 속에서 원석이 스스로 빛을 냅니다.",
    "growth": "손안의 묘목이 화면 밖으로 솟구쳐 오릅니다.",
    "bluechip": "두꺼운 방패가 땅에 박히고, 바람이 갈라집니다.",
    "analyst": "장부의 갈피가 열리고 숫자의 결이 드러납니다.",
    "holder": "지팡이를 감은 덩굴이 세월만큼 두꺼워졌습니다.",
    # ── 🤖 퀀트 ──
    "factor": "흩어진 조각들이 제자리를 찾아 격자로 맞물립니다.",
    "backtester": "지나간 시간이 되감기며 다시 한번 재생됩니다.",
    "arbitrageur": "벌어진 두 세계 사이의 틈이 또렷하게 보입니다.",
    "mlquant": "스스로 자란 회로가 답을 내놓습니다. 이유는 묻지 않습니다.",
    "riskmanager": "잃지 않을 만큼의 방벽이 조용히 세워집니다.",
    # ── 🐋 큰손 ──
    "institution": "거대한 그림자가 등 뒤에 섭니다. 이제 같은 편입니다.",
    "foreign": "밤을 건너온 바람이 판을 통째로 뒤집습니다.",
    "syndicate": "붓을 든 손이 차트 위에 선을 그리기 시작합니다.",
    "superant": "개미의 등딱지 위에 왕관이 얹힙니다.",
    "brokerdesk": "모든 주문이 그의 책상 위를 지나갑니다.",
    # ── 🔥 승부사 ──
    "allin": "손안의 불붙은 동전 하나. 나머지는 전부 걸었습니다.",
    "leveraged": "빌린 힘이 사슬처럼 팔을 감습니다. 달콤하고 무겁습니다.",
    "themesurfer": "발판이 뒤에서 무너지고 앞에서 새로 생깁니다.",
    "limithunter": "천장에 금이 갑니다. 뚫리는 그 한순간에만 존재합니다.",
    "averagedown": "내려갈수록 짐이 늘어납니다. 그래도 손을 놓지 않습니다.",
    # ── 🕯️ 관망자 ──
    "cashholder": "닫힌 궤짝 위에서 촛불이 미동도 없이 탑니다.",
    "shortseller": "활이 아래를 겨눕니다. 떨어지는 쪽에도 길이 있습니다.",
    "crashwaiter": "창고의 문이 닫히고, 긴 겨울을 기다립니다.",
    "hedger": "저울의 양쪽이 서로를 붙듭니다. 어느 쪽도 무너지지 않습니다.",
    "observer": "아무것도 하지 않습니다. 그것이 가장 어려운 매매입니다.",
    # ── 📡 정보꾼 ──
    "disclosure": "봉인이 뜯기고, 아직 아무도 읽지 않은 문장이 드러납니다.",
    "newsscanner": "소음이 걷히고 신호 하나만 또렷해집니다.",
    "reportcollector": "쌓인 리포트가 한 방향을 가리킵니다.",
    "rumorchaser": "진실보다 먼저 도착한 속삭임을 붙잡았습니다.",
    "earningsseer": "그릇의 수면 위로 다음 분기가 어른거립니다.",
    # ── 🌾 배당농부 ──
    "dividend": "낫이 완만한 호를 그리며 이삭을 벱니다.",
    "compounder": "작은 소용돌이가 스스로를 삼키며 커집니다.",
    "dcainvestor": "같은 날, 같은 자리에 또 한 알을 심습니다.",
    "reitlord": "품에 안은 탑이 대신 일하기 시작합니다.",
    "bondfarmer": "밀랍 봉인이 조용히 굳습니다. 화려하지 않지만 배신하지 않습니다.",
}


def awakening_flavor(class_key: str, rarity: str, growth: int) -> str:
    """각성 성공 시 보여줄 문구. 유저가 받은 이미지와 같은 것을 가리킨다."""
    if class_key not in CLASS_FLAVORS:
        raise KeyError(f"알 수 없는 직군: {class_key}")
    if rarity not in RARITY_FLAVORS:
        raise KeyError(f"알 수 없는 종: {rarity}")
    if growth not in GROWTH_FLAVORS:
        raise KeyError(f"알 수 없는 성장 단계: {growth}")

    return "\n".join(
        (
            RARITY_FLAVORS[rarity],
            CLASS_FLAVORS[class_key],
            GROWTH_FLAVORS[growth],
        )
    )


def class_label(class_key: str) -> str:
    """도감·랭킹에 쓸 표기 (예: '⚡ 스캘퍼')"""
    _family, name, emoji, _desc, _body = CLASS_ART[class_key]
    return f"{emoji} {name}"


def class_family(class_key: str) -> Tuple[str, str]:
    """직군이 속한 계열의 (이름, 이모지)"""
    family = CLASS_ART[class_key][0]
    return FAMILIES[family]


def classes_of(family: str) -> List[str]:
    """계열에 속한 직군 키 목록"""
    return [k for k, v in CLASS_ART.items() if v[0] == family]


def art_stem(class_key: str, rarity: str, growth: int) -> Optional[str]:
    """이 조합의 이미지 파일 이름. 조합이 잘못되면 None."""
    if class_key not in CLASS_ART or rarity not in RARITY_ART:
        return None
    if growth not in GROWTH_STAGES:
        return None
    return image_stem(class_key, rarity, growth)


# ===========================================
# 쪼렙 구간 (직군 배정 전)
# ===========================================
# 직군도 종도 없는 Lv.0~9 전용. 축이 성장 하나뿐이라 직군 그림과 번호를
# 공유하지 않는다. 섞으면 "각성 2단계"가 두 가지를 뜻하게 된다.
NOVICE_FLAVORS: Dict[int, str] = {
    1: "아직 이름도 없는 개미입니다. 손에 쥔 막대기 하나가 전부입니다.",
    2: "기운 옷과 무딘 검. 그래도 어제보다는 멀리 나가 봅니다.",
    3: "가죽 조끼를 입고 지도를 접어 넣습니다. 곧 무언가가 정해집니다.",
}


def novice_stage(level: int, class_level: int) -> int:
    """레벨 -> 쪼렙 단계(1~3).

    class_level은 직군을 받는 레벨이다. 그 직전까지를 균등하게 나눈다.
    """
    stages = len(NOVICE_ART)
    span = max(1, class_level)
    if level <= 0:
        return 1
    stage = int(level / (span / stages)) + 1
    return max(1, min(stage, stages))


def novice_stage_name(stage: int) -> str:
    return NOVICE_ART.get(stage, NOVICE_ART[1])[0]


def novice_art_stem(stage: int) -> Optional[str]:
    if stage not in NOVICE_ART:
        return None
    return novice_stem(stage)


def novice_flavor(stage: int) -> str:
    return NOVICE_FLAVORS.get(stage, NOVICE_FLAVORS[1])
