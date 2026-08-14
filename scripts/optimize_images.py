#!/usr/bin/env python3
"""
생성된 원본 PNG를 서빙용 WebP로 줄인다.

generate_images.py가 만드는 원본은 1536x1024 PNG로 장당 2MB가 넘는다.
600장이면 1.4GB라 깃에 넣을 수 없고, 애초에 그 해상도가 필요하지도 않다.
카카오 basicCard 썸네일은 실제로 폭 300px 안팎으로 축소돼 표시된다.

그래서 원본은 로컬 마스터로만 두고(.gitignore), 여기서 줄인 것만 커밋한다.
원본을 다시 만들려면 돈이 드니 원본 폴더는 지우지 마라.

사용법:
    python scripts/optimize_images.py                  # art/*.png -> art/web/*.webp
    python scripts/optimize_images.py --format jpeg    # 카카오가 webp를 못 그릴 때
    python scripts/optimize_images.py --force          # 이미 변환된 것도 다시
"""

import argparse
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Pillow가 필요합니다:  pip install pillow")
    sys.exit(1)

# 고해상도 화면을 감안해 표시 크기의 2배 정도만 남긴다.
# 이보다 키워도 카카오 카드에서는 차이를 볼 수 없다.
MAX_WIDTH = 1024
QUALITY = 82


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--srcdir", default="art")
    p.add_argument("--outdir", default="art/web")
    p.add_argument("--max-width", type=int, default=MAX_WIDTH)
    p.add_argument("--quality", type=int, default=QUALITY)
    p.add_argument(
        "--format",
        dest="fmt",
        default="webp",
        choices=["webp", "jpeg"],
        help="출력 포맷. 카카오가 webp를 못 그리면 jpeg로 (settings ART_EXT도 함께)",
    )
    p.add_argument("--force", action="store_true", help="이미 변환된 것도 다시")
    args = p.parse_args()

    src = Path(args.srcdir)
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    pngs = sorted(src.glob("*.png"))
    if not pngs:
        print(f"{src}에 png가 없습니다.")
        return 1

    before = after = 0
    converted = skipped = 0

    for path in pngs:
        target = out / f"{path.stem}.{args.fmt}"
        if target.exists() and not args.force:
            skipped += 1
            before += path.stat().st_size
            after += target.stat().st_size
            continue

        with Image.open(path) as im:
            im = im.convert("RGB")
            if im.width > args.max_width:
                height = round(im.height * args.max_width / im.width)
                im = im.resize((args.max_width, height), Image.LANCZOS)
            if args.fmt == "webp":
                im.save(target, "WEBP", quality=args.quality, method=6)
            else:
                im.save(target, "JPEG", quality=args.quality, optimize=True)

        before += path.stat().st_size
        after += target.stat().st_size
        converted += 1
        print(f"{path.name} -> {target.name} ({target.stat().st_size // 1024}KB)")

    ratio = (1 - after / before) * 100 if before else 0
    print(
        f"\n변환 {converted}장 / 건너뜀 {skipped}장\n"
        f"{before / 1024 / 1024:.1f}MB -> {after / 1024 / 1024:.1f}MB "
        f"({ratio:.0f}% 감소)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
