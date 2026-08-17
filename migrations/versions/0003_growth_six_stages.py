"""성장 단계를 3개에서 6개로 늘리면서 도감 기록의 좌표를 옮긴다

성장 단계가 각성/숙련/초월 셋이던 시절 30레벨을 3등분했더니, 직군을
Lv.10에 받는 탓에 1단계가 Lv.10 한 레벨에만 쓰이고 나머지는 열 레벨씩
같은 그림이었다. 이제 그림이 붙는 구간(Lv.10~30)을 6등분한다.

이미지 파일은 g2 -> g3, g3 -> g6으로 이름을 바꿨다(1·3·6이 옛 1·2·3).
`class_collections`에 이미 쌓인 기록도 같은 규칙으로 옮겨야, 유저가 예전에
연 '숙련' 칸이 새 번호 체계에서도 계속 숙련을 가리킨다. 안 옮기면 옛 g2
기록이 새 2단계(발현)를 뜻하게 되어, 열지 않은 칸이 열려 있고 연 칸은
비어 있는 상태가 된다.

순서가 중요하다. 2 -> 3을 먼저 하면 그 행이 다시 3 -> 6에 걸려 전부 6이
된다. 큰 번호부터 옮긴다.

Revision ID: 0003_growth_six_stages
Revises: 0002_class_collection
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_growth_six_stages"
down_revision: Union[str, None] = "0002_class_collection"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "class_collections"

# (옛 단계, 새 단계) - 큰 번호부터
_REMAP = ((3, 6), (2, 3))


def _table_exists(bind) -> bool:
    return sa.inspect(bind).has_table(TABLE)


def _move(bind, source: int, target: int) -> None:
    """growth=source인 기록을 target으로 옮긴다.

    옮길 자리에 이미 같은 (유저, 직군, 종) 기록이 있으면 유니크 제약에
    걸린다. 도감은 부가 기록이므로 그런 행은 지운다 - 어차피 같은 칸이다.
    """
    bind.execute(
        sa.text(
            f"DELETE FROM {TABLE} WHERE growth = :source AND EXISTS ("
            f"  SELECT 1 FROM {TABLE} other"
            f"  WHERE other.kakao_id = {TABLE}.kakao_id"
            f"    AND other.job = {TABLE}.job"
            f"    AND other.rarity = {TABLE}.rarity"
            f"    AND other.growth = :target)"
        ),
        {"source": source, "target": target},
    )
    bind.execute(
        sa.text(f"UPDATE {TABLE} SET growth = :target WHERE growth = :source"),
        {"source": source, "target": target},
    )


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind):
        # 0002가 만들기 전에는 옮길 기록 자체가 없다
        return
    for old, new in _REMAP:
        _move(bind, old, new)


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind):
        return
    # 되돌릴 때는 작은 번호부터. 3 -> 2를 먼저 하면 6 -> 3이 다시 2로 밀린다.
    for old, new in reversed(_REMAP):
        _move(bind, new, old)
