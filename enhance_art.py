"""
각성 직군 아트 프롬프트 데이터

이미지는 [공통 스타일] + [직군 본문] + [종 연출] + [성장 연출] 네 조각의
조합으로 만든다. 직군 본문만 늘리면 조합 수가 자동으로 늘어나므로,
직군을 100개로 확장해도 이 파일에 항목만 추가하면 된다.

순수 데이터만 담는다. 조합·생성 로직은 scripts/generate_images.py에 있다.
"""

# 모든 프롬프트 앞에 붙는 공통 블록.
# 도감은 낱장의 완성도보다 '나란히 놨을 때 한 세트로 보이는가'가 중요하다.
# 그래서 렌더 방식·배경·색 수를 여기서 강하게 고정한다.
COMMON_STYLE = (
    "cinematic 3D render, photorealistic materials, anthropomorphic ant hero, "
    "single subject centered, dynamic full-body action pose, "
    "empty dark void background with only abstract light streaks, "
    "strictly two-color palette plus black, dramatic rim lighting, "
    "shallow depth of field, high detail, wide cinematic 16:9 composition, "
    "absolutely no text, no numbers, no letters, no logos, no watermark"
)

# 종(희귀도) 연출.
# 도감을 훑을 때 등급이 즉시 읽혀야 하므로 연출 강도를 단계적으로 벌린다.
RARITY_ART = {
    "normal": ("노멀", "⬜", "clean render, minimal effects, matte finish"),
    "rare": ("레어", "🟦", "faint colored aura tracing the silhouette"),
    "epic": ("에픽", "🟪", "glowing aura, small fragments orbiting slowly"),
    "legend": (
        "전설",
        "🟧",
        "radiant energy corona, shattered debris suspended mid-air",
    ),
    "myth": (
        "신화",
        "🟨",
        "reality warping, impossible geometry, the frame itself fractures",
    ),
}

# 성장 단계 연출.
# 종을 못 뽑아도 레벨을 올리면 내 캐릭터가 멋있어지는 축.
GROWTH_ART = {
    1: (
        "각성",
        "young lean build, simple functional gear, clean unmarked carapace",
    ),
    2: (
        "숙련",
        "hardened build, layered refined armor with battle scars and "
        "etched sigils, confident weathered presence",
    ),
    3: (
        "초월",
        "imposing silhouette, armor transformed and partially self-luminous, "
        "trailing energy cape, overwhelming veteran presence",
    ),
}

# 계열: 직군을 묶는 상위 분류. 도감 정렬과 이미지 폴백에 쓴다.
FAMILIES = {
    "trader": ("트레이더", "⚡"),
    "investor": ("투자가", "📜"),
    "quant": ("퀀트", "🤖"),
    "whale": ("큰손", "🐋"),
    "gambler": ("승부사", "🔥"),
    "watcher": ("관망자", "🕯️"),
    "informant": ("정보꾼", "📡"),
    "farmer": ("배당농부", "🌾"),
}

# 직군 본문.
#   key: (계열, 이름, 이모지, 한 줄 설명, 이미지 프롬프트 본문)
#
# 프롬프트 본문에는 '무엇을 그릴지'만 쓴다. 렌더 방식·배경·등급 연출은
# 위의 공통/종/성장 블록이 담당하므로 여기서 반복하지 않는다.
CLASS_ART = {
    # ── ⚡ 트레이더 계열 ──────────────────────────────
    "scalper": (
        "trader",
        "스캘퍼",
        "⚡",
        "1초를 세 번 쪼갠다. 남들이 클릭할 때 그는 이미 나왔다.",
        "A razor-thin ant in a skintight matte-black bodysuit with crimson "
        "circuit lines, edges blurred from sheer speed, holding a single "
        "needle-like stiletto. Light trails streak past. "
        "Palette: matte black and crimson only.",
    ),
    "swinger": (
        "trader",
        "스윙어",
        "🌊",
        "파도를 타는 자. 꼭대기에서 팔고 골짜기에서 산다.",
        "An agile ant warrior riding a cresting wave of pure teal light, "
        "knees bent, arms wide, perfectly balanced mid-carve. Spray of "
        "glowing droplets trailing behind. "
        "Palette: teal and seafoam white only.",
    ),
    "momentum": (
        "trader",
        "모멘텀 헌터",
        "🎯",
        "오르는 것은 더 오른다. 그는 추세의 등에 올라탄다.",
        "A predatory ant archer drawing a longbow whose string is a taut "
        "beam of light, arrow already glowing, eyes narrowed on a distant "
        "target, cloak swept by wind. "
        "Palette: hunter green and burnt orange only.",
    ),
    "contrarian": (
        "trader",
        "역추세꾼",
        "📉",
        "모두가 던질 때 손을 내민다. 칼날을 잡는 자.",
        "An ant duelist catching a falling blade barehanded, red light "
        "dripping from the grip, expression utterly calm while everything "
        "around him descends. "
        "Palette: deep red and steel grey only.",
    ),
    "orderflow": (
        "trader",
        "호가 사냥꾼",
        "🔍",
        "호가창의 미세한 떨림에서 큰손의 발자국을 읽는다.",
        "An ant tracker crouched low, one claw touching a faintly glowing "
        "grid on the ground like footprints in snow, a monocle lens over "
        "one compound eye, reading something invisible. "
        "Palette: ice blue and graphite only.",
    ),
    # ── 📜 투자가 계열 ──────────────────────────────
    "valuehunter": (
        "investor",
        "가치 발굴자",
        "💎",
        "시장이 버린 돌에서 원석을 골라낸다.",
        "An ant prospector with a mining pick and lantern, kneeling in a "
        "dark seam, holding up a rough uncut gem that glows from within. "
        "Dust, sweat, patience. "
        "Palette: lantern gold and gem blue only.",
    ),
    "growth": (
        "investor",
        "성장 신봉자",
        "🌱",
        "지금 비싼 게 아니라, 미래가 아직 안 왔을 뿐이다.",
        "An ant caretaker cupping a small sapling that emits a soft vertical "
        "beam of green light shooting upward beyond the frame, both claws "
        "protective, hopeful expression. "
        "Palette: spring green and warm white only.",
    ),
    "bluechip": (
        "investor",
        "우량주 수호자",
        "🏦",
        "무너지지 않는 것에만 돈을 둔다.",
        "A stoic ant sentinel in polished plate armor standing before a "
        "colossal carved pillar, tower shield planted in the ground, "
        "utterly immovable. "
        "Palette: marble white and steel blue only.",
    ),
    "analyst": (
        "investor",
        "재무제표 해부가",
        "🔬",
        "숫자는 거짓말하지 않는다. 사람이 할 뿐이다.",
        "An ant surgeon-analyst in a clean apron, scalpel in one claw, "
        "dissecting a glowing document laid open like an anatomy specimen "
        "under cold focused light from above. "
        "Palette: clinical white and vein red only.",
    ),
    "holder": (
        "investor",
        "장기 보유자",
        "⏳",
        "10년을 버틴 자에게만 열리는 문이 있다.",
        "An ancient weathered ant seated cross-legged, vines and dust grown "
        "over the armor, an hourglass beside him nearly emptied, eyes "
        "closed, utterly still. "
        "Palette: mossy green and dust gold only.",
    ),
}


def build_prompt(class_key: str, rarity: str, growth: int) -> str:
    """[공통] + [직군] + [종] + [성장] 조합으로 최종 프롬프트를 만든다"""
    if class_key not in CLASS_ART:
        raise KeyError(f"알 수 없는 직군: {class_key}")
    if rarity not in RARITY_ART:
        raise KeyError(f"알 수 없는 종: {rarity}")
    if growth not in GROWTH_ART:
        raise KeyError(f"알 수 없는 성장 단계: {growth}")

    body = CLASS_ART[class_key][4]
    rarity_fx = RARITY_ART[rarity][2]
    growth_fx = GROWTH_ART[growth][1]
    return f"{COMMON_STYLE}. {body} {growth_fx}. {rarity_fx}."


def all_combinations():
    """생성해야 할 (직군, 종, 성장) 조합 전체"""
    for class_key in CLASS_ART:
        for rarity in RARITY_ART:
            for growth in GROWTH_ART:
                yield class_key, rarity, growth
