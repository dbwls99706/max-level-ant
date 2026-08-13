#!/usr/bin/env python3
"""
받아 둔 이미지가 온전한지 검사한다.

생성 중에 강제종료하면 쓰다 만 PNG가 남을 수 있다. 그 파일은 크기가
0이 아니어서 다음 실행 때 "이미 있음"으로 건너뛰어지고, 도감에서야
깨진 그림으로 드러난다. 재개 전에 걸러내는 편이 싸다.

사용법:
    python scripts/verify_images.py            # 검사만
    python scripts/verify_images.py --delete   # 깨진 파일 삭제 (다음 실행 때 다시 받음)
"""

import argparse
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Pillow가 필요합니다:  pip install pillow")
    sys.exit(1)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--srcdir", default="art")
    p.add_argument("--delete", action="store_true", help="깨진 파일 삭제")
    args = p.parse_args()

    pngs = sorted(Path(args.srcdir).glob("*.png"))
    if not pngs:
        print(f"{args.srcdir}에 png가 없습니다.")
        return 1

    broken = []
    for path in pngs:
        try:
            # verify()는 헤더만 보므로, 잘린 파일은 load()까지 해야 잡힌다
            with Image.open(path) as im:
                im.load()
        except Exception as e:
            broken.append((path, e))

    print(f"검사 {len(pngs)}장 / 손상 {len(broken)}장")
    for path, e in broken:
        print(f"  {path.name}: {type(e).__name__} {e}")
        if args.delete:
            path.unlink()

    if broken and not args.delete:
        print(
            "\n--delete 를 붙이면 지웁니다. 지운 뒤 생성 명령을 다시 돌리면 채워집니다."
        )
    return 1 if broken and not args.delete else 0


if __name__ == "__main__":
    sys.exit(main())
