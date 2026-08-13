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
    "dark uncluttered background with only abstract light streaks, "
    "two dominant colors, "
    # 강한 key light가 없으면 어두운 색 직군이 배경에 묻혀 형체가 안 보인다.
    # 카카오 카드에서는 작게 표시되므로 실루엣이 또렷해야 한다.
    "strong key light on the subject plus rim lighting, "
    "subject clearly readable and well separated from the background, "
    "high detail, wide cinematic 16:9 composition, "
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
    # "reality warping / the frame fractures" 같은 표현은 moderation에 걸렸다.
    # 파괴·왜곡을 연상시키는 단어를 빼고 '빛과 신성함'으로 최고 등급을 표현한다.
    "myth": (
        "신화",
        "🟨",
        "brilliant golden light bending around the figure, luminous halo, "
        "swirling cosmic energy, transcendent divine presence",
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
#
# 주식 모티프는 배경이 아니라 '무기와 소품'에만 녹인다. 배경에 차트를 깔면
# 화면이 지저분해지고 이미지 모델이 숫자·문자를 그려 넣기 시작한다
# (초기 시안에서 실제로 보드에 글자가 박혔다). 형태로만 은유한다.
CLASS_ART = {
    # ── ⚡ 트레이더 계열 ──────────────────────────────
    "scalper": (
        "trader",
        "스캘퍼",
        "⚡",
        "1초를 세 번 쪼갠다. 남들이 클릭할 때 그는 이미 나왔다.",
        "A lean swift ant courier in sleek charcoal-grey armor with glowing "
        "crimson accent lines, edges blurred from sheer speed, wielding a "
        "slender glowing blade shaped like a single thin candlestick wick. "
        "Bright light trails streak past. Palette: charcoal grey and crimson.",
    ),
    "swinger": (
        "trader",
        "스윙어",
        "🌊",
        "파도를 타는 자. 꼭대기에서 팔고 골짜기에서 산다.",
        "An agile ant warrior riding a cresting wave of pure teal light, "
        "knees bent, arms wide, balanced on a narrow board carved as a "
        "smooth rising-and-falling curve. Spray of glowing droplets. "
        "Palette: teal and seafoam white.",
    ),
    "momentum": (
        "trader",
        "모멘텀 헌터",
        "🎯",
        "오르는 것은 더 오른다. 그는 추세의 등에 올라탄다.",
        "A predatory ant archer drawing a longbow whose string is a taut "
        "steeply rising beam of light, the arrow itself a sharp upward "
        "arrowhead of energy, cloak swept by wind. "
        "Palette: hunter green and burnt orange.",
    ),
    "contrarian": (
        "trader",
        "역추세꾼",
        "📉",
        "모두가 던질 때 손을 내민다. 칼날을 잡는 자.",
        "An ant duelist catching a falling red blade barehanded, the blade "
        "shaped like a steep descending bar, red light dripping from the "
        "grip, expression utterly calm. Palette: deep red and steel grey.",
    ),
    "orderflow": (
        "trader",
        "호가 사냥꾼",
        "🔍",
        "호가창의 미세한 떨림에서 큰손의 발자국을 읽는다.",
        "An ant tracker crouched low, one claw touching a faint glowing "
        "ladder of stacked horizontal light bars rising from the ground "
        "like footprints, a monocle lens over one compound eye. "
        "Palette: ice blue and graphite.",
    ),
    # ── 📜 투자가 계열 ──────────────────────────────
    "valuehunter": (
        "investor",
        "가치 발굴자",
        "💎",
        "시장이 버린 돌에서 원석을 골라낸다.",
        "An ant prospector with a mining pick and a lantern, kneeling in a "
        "dark seam, holding up a rough uncut gem glowing from within. "
        "Dust, sweat, patience. Palette: lantern gold and gem blue.",
    ),
    "growth": (
        "investor",
        "성장 신봉자",
        "🌱",
        "지금 비싼 게 아니라, 미래가 아직 안 왔을 뿐이다.",
        "An ant caretaker cupping a small sapling whose stem is a smooth "
        "curve accelerating upward into a beam of green light beyond the "
        "frame, both claws protective. Palette: spring green and warm white.",
    ),
    "bluechip": (
        "investor",
        "우량주 수호자",
        "🏦",
        "무너지지 않는 것에만 돈을 둔다.",
        "A stoic ant sentinel in polished plate armor before a colossal "
        "carved pillar, holding a heavy tower shield forged in the shape of "
        "a broad stable horizontal bar. Palette: marble white and steel blue.",
    ),
    "analyst": (
        "investor",
        "재무제표 해부가",
        "🔬",
        "숫자는 거짓말하지 않는다. 사람이 할 뿐이다.",
        "An ant surgeon-analyst in a clean apron, scalpel in one claw, "
        "dissecting a glowing ledger sheet laid open like an anatomy "
        "specimen under cold focused light. Palette: clinical white and "
        "vein red.",
    ),
    "holder": (
        "investor",
        "장기 보유자",
        "⏳",
        "10년을 버틴 자에게만 열리는 문이 있다.",
        "An ancient weathered ant seated cross-legged, vines grown over the "
        "armor, gripping a long staff whose shaft is one unbroken slowly "
        "rising line, an hourglass beside him nearly empty. "
        "Palette: mossy green and dust gold.",
    ),
    # ── 🤖 퀀트 계열 ──────────────────────────────
    "factor": (
        "quant",
        "팩터 설계자",
        "📐",
        "수익의 원인을 조각내어 이름을 붙인다.",
        "An ant architect in matte-white composite plating with a seamless "
        "visor, assembling floating geometric tiles into a precise lattice "
        "with both claws, each tile a clean glowing polygon. "
        "Palette: matte white and pale cyan.",
    ),
    "backtester": (
        "quant",
        "백테스터",
        "⏪",
        "과거를 수천 번 되돌려 미래를 시험한다.",
        "An ant technician surrounded by concentric rotating rings of light, "
        "one claw pulling a ring backward as ghosted afterimages of the same "
        "ant trail behind. Palette: gunmetal grey and electric violet.",
    ),
    "arbitrageur": (
        "quant",
        "아비트라저",
        "⚙️",
        "두 시장의 틈에서 무위험 이익을 줍는다.",
        "An ant operator standing between two mirrored floating plates of "
        "light held level by a delicate balance beam, harvesting a bright "
        "spark from the narrow gap between them. "
        "Palette: brushed steel and mint green.",
    ),
    "mlquant": (
        "quant",
        "머신러닝 트레이더",
        "🧬",
        "모델이 무엇을 배웠는지는 그도 모른다.",
        "An ant handler with a translucent neural lattice of branching light "
        "threads blooming from the back of the skull, eyes replaced by a "
        "thin scanning line. Palette: deep indigo and bioluminescent lime.",
    ),
    "riskmanager": (
        "quant",
        "리스크 관리자",
        "🛡️",
        "얼마를 버느냐보다 얼마를 잃지 않느냐.",
        "A disciplined ant officer holding a wide circular shield whose "
        "surface is a smooth bell-shaped dome of light, one claw raised in "
        "a halt gesture. Palette: slate blue and warning amber.",
    ),
    # ── 🐋 큰손 계열 ──────────────────────────────
    "institution": (
        "whale",
        "기관",
        "🏛️",
        "개인의 반대편에는 언제나 그들이 있다.",
        "A towering ant executive in a heavy double-breasted coat of "
        "midnight blue with gold trim, arms crossed, utterly immovable, "
        "a colossal stone seal ring on one claw. "
        "Palette: midnight blue and heavy gold.",
    ),
    "foreign": (
        "whale",
        "외국인",
        "🌍",
        "밤사이 들어와 아침에 판을 바꾼다.",
        "An ant envoy in a long travel coat with a wide brim, standing "
        "before a slowly rotating globe of cold light, one claw resting on "
        "a heavy travel case. Palette: deep navy and pale silver.",
    ),
    "syndicate": (
        "whale",
        "세력",
        "🎭",
        "차트는 그림이다. 그리는 자가 따로 있다.",
        "A shadowed ant figure in a high-collared cloak holding a fine "
        "brush that paints a glowing rising line in the air, face half "
        "hidden behind a smooth featureless mask. "
        "Palette: black violet and sickly gold.",
    ),
    "superant": (
        "whale",
        "슈퍼개미",
        "👑",
        "개미로 시작해 판을 흔드는 자리에 올랐다.",
        "A broad-shouldered ant in a tailored coat over worn old armor, "
        "one plated claw and one bare, standing tall on a small mound of "
        "gleaming coins. Palette: royal purple and warm gold.",
    ),
    "brokerdesk": (
        "whale",
        "창구의 주인",
        "📞",
        "모든 주문이 그의 책상을 지나간다.",
        "An ant desk-master seated behind a wide curved console of glowing "
        "switches, many claws working at once, an antique handset raised to "
        "the head. Palette: mahogany brown and lamp amber.",
    ),
    # ── 🔥 승부사 계열 ──────────────────────────────
    "allin": (
        "gambler",
        "몰빵러",
        "💥",
        "반토막이거나 두 배거나. 중간은 없다.",
        "A grinning reckless ant in a torn scarlet coat with burning edges, "
        "one arm raised holding a single blazing coin between two claws, "
        "embers swirling upward. Palette: scarlet and ember orange.",
    ),
    "leveraged": (
        "gambler",
        "레버리지 중독자",
        "⛓️",
        "빌린 힘은 달콤하고, 청산은 조용히 온다.",
        "A straining ant warrior gripping a massive weapon far too large "
        "for its frame, glowing chains coiled around both arms pulling in "
        "opposite directions. Palette: molten orange and iron black.",
    ),
    "themesurfer": (
        "gambler",
        "테마주 서퍼",
        "🏄",
        "이번 주의 이야기에 올라탄다. 다음 주는 다음 주에.",
        "A nimble ant leaping between drifting glowing platforms, mid-air, "
        "one platform already dissolving behind, another forming ahead. "
        "Palette: hot pink and cyan.",
    ),
    "limithunter": (
        "gambler",
        "상한가 사냥꾼",
        "🚀",
        "천장을 뚫는 순간에만 존재한다.",
        "An ant striker mid-uppercut smashing through a horizontal ceiling "
        "plate of red light that shatters into rising shards. "
        "Palette: blazing red and white hot.",
    ),
    "averagedown": (
        "gambler",
        "물타기 장인",
        "🌊",
        "내려갈수록 더 산다. 평단은 신앙이다.",
        "A waist-deep submerged ant calmly pouring more glowing liquid from "
        "a jug into the rising water around itself, expression serene. "
        "Palette: deep ocean blue and pale gold.",
    ),
    # ── 🕯️ 관망자 계열 ──────────────────────────────
    "cashholder": (
        "watcher",
        "현금 보유자",
        "💵",
        "현금도 포지션이다.",
        "A hooded ant ascetic seated in shadow beside a single candle, "
        "hands folded over a closed heavy chest, flame perfectly still. "
        "Palette: near black and warm candle amber.",
    ),
    "shortseller": (
        "watcher",
        "공매도꾼",
        "🔻",
        "떨어지는 쪽에도 돈이 있다.",
        "An inverted ant hunter descending headfirst with controlled grace, "
        "a downward-pointing spear of cold light in one claw. "
        "Palette: deep teal and pale bone white.",
    ),
    "crashwaiter": (
        "watcher",
        "폭락 대기자",
        "🧊",
        "그는 겨울을 기다리며 창고를 채운다.",
        "A cloaked ant sentinel standing perfectly still in falling ash, "
        "a heavy iron key held in one claw, unmoved while everything "
        "around descends. Palette: frost grey and cold blue.",
    ),
    "hedger": (
        "watcher",
        "헤지 설계자",
        "⚖️",
        "한쪽이 무너져도 다른 쪽이 버틴다.",
        "An ant engineer holding a perfectly level balance beam with a "
        "glowing weight suspended at each end, calm and precise. "
        "Palette: cool grey and balanced green.",
    ),
    "observer": (
        "watcher",
        "침묵의 관찰자",
        "👁️",
        "아무것도 하지 않는 것이 가장 어려운 매매다.",
        "A motionless ant monk seated in lotus position, eyes closed, a "
        "single ring of faint light hovering above, absolutely no motion "
        "blur anywhere. Palette: stone grey and soft white.",
    ),
    # ── 📡 정보꾼 계열 ──────────────────────────────
    "disclosure": (
        "informant",
        "공시 사냥꾼",
        "📜",
        "공시가 뜨기 3초 전, 그는 이미 알고 있다.",
        "A wiry ant scout with antenna-like sensors sprouting from the head, "
        "one claw pressed to an earpiece, a freshly torn blank scroll "
        "fluttering from the other claw. Palette: slate grey and signal green.",
    ),
    "newsscanner": (
        "informant",
        "뉴스 스캐너",
        "📰",
        "세상의 소음에서 신호만 건져낸다.",
        "An ant operator behind a wide fan of floating blank paper sheets, "
        "sweeping a beam of light across them, one sheet pulled out and "
        "glowing. Palette: newsprint grey and highlight yellow.",
    ),
    "reportcollector": (
        "informant",
        "리포트 수집가",
        "📚",
        "애널리스트의 목표주가를 모으는 사람.",
        "An ant archivist in a tall vault of stacked blank folios, arms "
        "full, one folio open and glowing softly. "
        "Palette: library brown and warm parchment.",
    ),
    "rumorchaser": (
        "informant",
        "소문 추적자",
        "🐺",
        "진실보다 빠른 것은 소문이다.",
        "A lean ant tracker in a hooded wrap following faint drifting wisps "
        "of whispering light through darkness, head turned mid-listen. "
        "Palette: smoke grey and pale violet.",
    ),
    "earningsseer": (
        "informant",
        "실적 예측가",
        "🔮",
        "다음 분기를 먼저 본 자가 이긴다.",
        "An ant seer bent over a shallow bowl of luminous liquid showing a "
        "rising glow, both claws framing it, face lit from below. "
        "Palette: deep purple and prophetic cyan.",
    ),
    # ── 🌾 배당농부 계열 ──────────────────────────────
    "dividend": (
        "farmer",
        "배당 수확자",
        "🌾",
        "심고, 기다리고, 거둔다.",
        "A sturdy weathered ant farmer in a wide straw hat resting both "
        "claws on a scythe whose blade is a smooth gently rising arc, rows "
        "of golden coin-topped stalks behind. "
        "Palette: harvest gold and earth brown.",
    ),
    "compounder": (
        "farmer",
        "복리 재배자",
        "🌀",
        "가장 느리고 가장 확실한 무기.",
        "An ant gardener tending a spiral-shelled plant that coils outward "
        "in ever-widening glowing rings, each ring brighter than the last. "
        "Palette: deep green and radiant gold.",
    ),
    "dcainvestor": (
        "farmer",
        "적립식 투자자",
        "📅",
        "매달 같은 날, 같은 금액. 그게 전부다.",
        "A methodical ant in simple work clothes dropping one glowing coin "
        "into a tall clear vessel already layered with identical coins in "
        "even bands. Palette: steady blue and coin silver.",
    ),
    "reitlord": (
        "farmer",
        "리츠 지주",
        "🏢",
        "건물이 대신 일하게 한다.",
        "A composed ant landholder in a long coat standing before tall "
        "monolithic blocks, a heavy ring of keys hanging at the belt. "
        "Palette: concrete grey and brass gold.",
    ),
    "bondfarmer": (
        "farmer",
        "채권 농부",
        "📜",
        "화려하지 않지만 배신하지 않는다.",
        "A calm elderly ant in a quilted coat holding a rolled sealed "
        "certificate with a wax seal, standing in an even field of low "
        "steady light. Palette: muted sage and aged ivory.",
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
