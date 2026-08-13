#!/usr/bin/env python3
"""
각성 직군 이미지 생성기 (OpenAI Images API)

이미지는 한 번만 만들어 두고 정적으로 서빙한다. 런타임에 생성하지 않는다.
카카오 스킬은 5초 안에 응답해야 하는데 이미지 생성은 수 초 이상 걸리고,
유저 요청마다 과금되기 때문이다.

사용법:
    # API 키 설정
    export OPENAI_API_KEY="sk-..."       # macOS / Linux
    $env:OPENAI_API_KEY = "sk-..."       # Windows PowerShell

    # 1) 맛보기 - 기본 3장만, 가장 싼 설정
    python scripts/generate_images.py --test

    # 2) 프롬프트가 확정되면 전량
    python scripts/generate_images.py --all

    # 3) 특정 직군만 다시
    python scripts/generate_images.py --class scalper

이미 파일이 있으면 건너뛰므로, 중단해도 다시 실행하면 이어서 받는다.
비용이 실제로 청구되므로 실행 전에 예상 금액을 보여주고 확인을 받는다.

원본 PNG는 장당 2MB가 넘어 저장소에 넣지 않는다(.gitignore).
서빙용으로 줄이려면 생성이 끝난 뒤 scripts/optimize_images.py를 돌린다.
"""

import argparse
import base64
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from enhance_art import (  # noqa: E402
    CLASS_ART,
    GROWTH_ART,
    RARITY_ART,
    all_combinations,
    build_prompt,
)

API_URL = "https://api.openai.com/v1/images/generations"

# 1536x1024 기준 장당 단가 (USD).
# 실측 표시가 붙은 것만 실제 청구액에서 역산한 값이다. 나머지는 그 비율로
# 공개 가격표를 보정한 추정치라 실제 청구액과 다를 수 있다.
# 예상 비용을 보여주기 위한 용도이지 정산용이 아니다.
#
# 추정치는 실제로 30%까지 빗나갔다 (1.5/medium을 0.034로 잡았는데 0.044였다).
# 큰 배치를 돌리기 전에 50장쯤에서 대시보드로 한 번 검산하는 게 안전하다.
PRICE_TABLE = {
    ("gpt-image-1-mini", "low"): 0.0053,  # 실측 (3장 $0.016)
    ("gpt-image-1-mini", "medium"): 0.011,
    ("gpt-image-1-mini", "high"): 0.036,
    ("gpt-image-1.5", "low"): 0.012,
    ("gpt-image-1.5", "medium"): 0.044,  # 실측 (66장 $2.91)
    ("gpt-image-1.5", "high"): 0.172,
}

# 카카오 basicCard 썸네일은 가로형이다. 정사각형으로 뽑으면 위아래가 잘린다.
DEFAULT_SIZE = "1536x1024"

# PRICE_TABLE(1536x1024) 대비 크기별 단가 배율. 픽셀 수 비율로 어림잡는다.
SIZE_FACTOR = {
    "1536x1024": 1.0,
    "1024x1536": 1.0,
    "1024x1024": 1024 / 1536,
}

# 맛보기용 조합.
# 축을 하나씩만 바꿔서, 어느 블록이 실제로 그림에 반영되는지 분리해 본다.
#   1. 스캘퍼 노멀 1단계     - 기준선. 어두운 팔레트가 배경에 묻히지 않는지
#   2. 스캘퍼 노멀 3단계     - 1번과 성장만 다르다. 장비가 실제로 늘어나는지
#   3. 스캘퍼 신화 3단계     - 2번과 종만 다르다. 등급 연출이 얹히는지
#   4. 가치 발굴자 노멀 1단계 - 1번과 직군만 다르다. 그림체가 한 세트로 붙는지
TEST_COMBOS = [
    ("scalper", "normal", 1),
    ("scalper", "normal", 3),
    ("scalper", "myth", 3),
    ("valuehunter", "normal", 1),
]


def family_sample():
    """계열마다 첫 직군 한 장씩. 조건을 고정해 계열 간 그림체만 비교한다.

    TEST_COMBOS로는 8계열 중 2개밖에 못 본다. 전량을 돌리기 전에
    나머지 계열이 같은 세트로 붙는지 싸게 확인하는 용도다.
    """
    seen = set()
    for class_key, (family, *_rest) in CLASS_ART.items():
        if family in seen:
            continue
        seen.add(family)
        yield class_key, "normal", 2


def out_path(outdir: Path, class_key: str, rarity: str, growth: int) -> Path:
    return outdir / f"{class_key}__{rarity}__g{growth}.png"


def estimate_cost(count: int, model: str, quality: str, size: str) -> float:
    unit = PRICE_TABLE.get((model, quality))
    if unit is None:
        return 0.0
    # PRICE_TABLE 자체가 1536x1024 기준이므로 여기서 또 곱하면 안 된다.
    # 정사각형으로 뽑을 때만 픽셀 수 비율(1024*1024 / 1536*1024)로 낮춰 잡는다.
    return count * unit * (SIZE_FACTOR.get(size, 1.0))


def generate_one(prompt: str, model: str, quality: str, size: str, retries: int):
    """이미지 한 장 생성. 성공하면 PNG 바이트, 실패하면 None."""
    payload = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "quality": quality,
        "n": 1,
    }
    headers = {
        "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
        "Content-Type": "application/json",
    }

    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=180)
        except requests.RequestException as e:
            print(f"    네트워크 오류 ({attempt}/{retries}): {e}")
            time.sleep(2**attempt)
            continue

        if resp.status_code == 200:
            data = resp.json()["data"][0]
            return base64.b64decode(data["b64_json"])

        # 429(유량)·5xx는 기다렸다 재시도할 가치가 있다.
        # 4xx는 요청 자체가 잘못된 것이라 재시도해도 같은 결과다.
        if resp.status_code == 429 or resp.status_code >= 500:
            wait = 2**attempt
            print(f"    {resp.status_code} - {wait}초 후 재시도 ({attempt}/{retries})")
            time.sleep(wait)
            continue

        # moderation 차단은 재시도해도 같은 결과다. 프롬프트 단어를 바꿔야 하므로
        # 다른 4xx와 구분해서 알려준다.
        if _is_moderation_block(resp):
            print("    차단: moderation - 프롬프트 단어를 바꿔야 합니다")
            print(f"      {prompt[-160:]}")
            return None

        print(f"    실패 {resp.status_code}: {resp.text[:300]}")
        return None

    return None


def _is_moderation_block(resp) -> bool:
    """안전 시스템에 막힌 응답인지"""
    if resp.status_code != 400:
        return False
    try:
        code = (resp.json().get("error") or {}).get("code") or ""
    except ValueError:
        return False
    return "moderation" in code


def run(combos, args) -> int:
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    todo = [c for c in combos if args.force or not out_path(outdir, *c).exists()]
    skipped = len(combos) - len(todo)

    print(f"모델   : {args.model} / {args.quality} / {args.size}")
    print(f"저장   : {outdir}")
    print(f"대상   : {len(combos)}장 (이미 있음 {skipped}장 건너뜀 -> {len(todo)}장)")
    if not todo:
        print("생성할 것이 없습니다.")
        return 0

    cost = estimate_cost(len(todo), args.model, args.quality, args.size)
    print(f"예상 비용: 약 ${cost:.2f} (추정치, 실제 청구액과 다를 수 있음)")

    if not args.yes:
        answer = input("진행할까요? [y/N] ").strip().lower()
        if answer != "y":
            print("취소했습니다.")
            return 1

    # 장당 30초가 넘게 걸려서 직렬로 600장을 돌리면 5시간이다.
    # API는 동시 요청을 받으므로 직렬로 기다릴 이유가 없다.
    # 429는 generate_one이 지수 백오프로 이미 처리한다.
    done = 0
    lock = threading.Lock()

    def work(combo):
        nonlocal done
        class_key, rarity, growth = combo
        family, name, emoji, _desc, _body = CLASS_ART[class_key]
        label = f"{emoji} {name} / {RARITY_ART[rarity][0]} / {GROWTH_ART[growth][0]}"
        prompt = build_prompt(class_key, rarity, growth)
        image = generate_one(prompt, args.model, args.quality, args.size, args.retries)
        path = out_path(outdir, class_key, rarity, growth)

        # 진행 출력과 파일 쓰기는 한 번에 하나씩. 여러 스레드가 섞여 찍히면
        # 어느 줄이 어느 장의 결과인지 읽을 수 없다.
        with lock:
            done += 1
            head = f"[{done}/{len(todo)}] {label}"
            if image is None:
                print(f"{head}\n    -> 실패")
                return None
            path.write_bytes(image)
            print(f"{head}\n    -> {path.name} ({len(image) // 1024}KB)")

        return {
            "file": path.name,
            "class": class_key,
            "family": family,
            "name": name,
            "rarity": rarity,
            "growth": growth,
            "prompt": prompt,
        }

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = list(pool.map(work, todo))

    manifest = [r for r in results if r]
    ok = len(manifest)
    fail = len(results) - ok

    if manifest:
        mpath = outdir / "manifest.json"
        existing = []
        if mpath.exists():
            existing = json.loads(mpath.read_text())
        merged = {m["file"]: m for m in existing}
        merged.update({m["file"]: m for m in manifest})
        mpath.write_text(
            json.dumps(list(merged.values()), ensure_ascii=False, indent=2)
        )
        print(f"\nmanifest 갱신: {mpath}")

    print(f"\n완료: 성공 {ok} / 실패 {fail}")
    return 0 if fail == 0 else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--test", action="store_true", help="맛보기 조합만 생성 (4장)")
    p.add_argument(
        "--sample-families",
        action="store_true",
        help="계열마다 한 장씩 생성 (8장). 전량 전 그림체 일관성 확인용",
    )
    p.add_argument("--all", action="store_true", help="전체 조합 생성")
    p.add_argument("--class", dest="class_key", help="특정 직군만 생성")
    p.add_argument(
        "--limit", type=int, default=0, help="생성 장수 상한 (0이면 제한 없음)"
    )
    p.add_argument("--model", default="gpt-image-1-mini", help="기본값이 가장 저렴")
    p.add_argument("--quality", default="low", choices=["low", "medium", "high"])
    p.add_argument("--size", default=DEFAULT_SIZE)
    p.add_argument("--outdir", default="art")
    p.add_argument("--retries", type=int, default=3)
    p.add_argument(
        "--concurrency",
        type=int,
        default=6,
        help="동시 생성 수. 429가 자주 뜨면 낮춰라",
    )
    p.add_argument("--force", action="store_true", help="이미 있는 파일도 다시 생성")
    p.add_argument("-y", "--yes", action="store_true", help="확인 없이 진행")
    args = p.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY 환경변수가 필요합니다.")
        print('  macOS/Linux : export OPENAI_API_KEY="sk-..."')
        print('  PowerShell  : $env:OPENAI_API_KEY = "sk-..."')
        return 1

    if args.test:
        combos = list(TEST_COMBOS)
    elif args.sample_families:
        combos = list(family_sample())
    elif args.class_key:
        combos = [c for c in all_combinations() if c[0] == args.class_key]
        if not combos:
            print(f"알 수 없는 직군: {args.class_key}")
            print(f"사용 가능: {', '.join(CLASS_ART)}")
            return 1
    elif args.all:
        combos = list(all_combinations())
    else:
        p.print_help()
        return 1

    if args.limit:
        combos = combos[: args.limit]

    return run(combos, args)


if __name__ == "__main__":
    sys.exit(main())
