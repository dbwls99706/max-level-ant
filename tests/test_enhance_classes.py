"""
각성 직군/종/성장 데이터 테스트

이미지 600장과 문구는 같은 (직군, 종, 성장) 좌표를 가리켜야 한다.
한쪽만 바뀌면 유저는 A 그림을 받고 B 설명을 읽게 되는데, 그건 서버
로그에 아무것도 남기지 않는다. 그래서 대응 관계를 여기서 못박는다.
"""

from collections import Counter
from pathlib import Path

import pytest

import enhance_art as ea
import enhance_classes as ec
from enhance_art import CLASS_ART, RARITY_ART, all_combinations
from enhance_config import EnhanceConfig
from settings import AssetConfig


class TestFlavorCoverage:
    """문구가 모든 좌표를 덮는지"""

    def test_every_class_has_a_flavor(self):
        """직군을 추가하고 문구를 빼먹으면 각성 성공 화면이 비어 버린다"""
        missing = [k for k in CLASS_ART if k not in ec.CLASS_FLAVORS]
        assert not missing, f"문구 없는 직군: {missing}"

    def test_no_flavor_for_unknown_class(self):
        """직군 이름을 바꾸고 문구를 안 지우면 영영 안 쓰이는 문구가 남는다"""
        orphans = [k for k in ec.CLASS_FLAVORS if k not in CLASS_ART]
        assert not orphans, f"쓰이지 않는 문구: {orphans}"

    def test_every_rarity_and_growth_has_a_flavor(self):
        assert set(ec.RARITY_FLAVORS) == set(RARITY_ART)
        assert set(ec.GROWTH_FLAVORS) == set(ec.GROWTH_STAGES)

    def test_every_combination_produces_text(self):
        """모든 조합이 문구를 만들어야 한다"""
        for class_key, rarity, growth in all_combinations():
            text = ec.awakening_flavor(class_key, rarity, growth)
            assert text.count("\n") == 2, f"{class_key}/{rarity}/g{growth}"
            assert all(line.strip() for line in text.split("\n"))

    def test_flavors_are_distinct_per_combination(self):
        """조합마다 다른 문장이어야 도감을 모으는 맛이 난다"""
        combos = list(all_combinations())
        seen = {ec.awakening_flavor(*c) for c in combos}
        assert len(seen) == len(combos), (
            f"중복 문구가 있다: {len(combos) - len(seen)}개"
        )

    def test_unknown_key_raises(self):
        with pytest.raises(KeyError):
            ec.awakening_flavor("nope", "normal", 1)
        with pytest.raises(KeyError):
            ec.awakening_flavor("scalper", "nope", 1)
        with pytest.raises(KeyError):
            ec.awakening_flavor("scalper", "normal", 9)


class TestFlavorMatchesArt:
    """문구와 이미지가 같은 좌표를 가리키는지"""

    def test_stem_matches_the_served_file(self):
        art_dir = Path(AssetConfig.DIRECTORY)
        if not art_dir.is_dir():
            pytest.skip(f"{art_dir} 없음")

        for class_key, rarity, growth in all_combinations():
            stem = ec.art_stem(class_key, rarity, growth)
            assert stem is not None
            assert (art_dir / f"{stem}.{AssetConfig.EXT}").exists(), stem

    def test_invalid_combination_has_no_stem(self):
        assert ec.art_stem("nope", "normal", 1) is None
        assert ec.art_stem("scalper", "nope", 1) is None
        assert ec.art_stem("scalper", "normal", 9) is None


class TestGrowthStage:
    """레벨에서 성장 단계로"""

    THRESHOLD = EnhanceConfig.CLASS_LEVEL_THRESHOLD
    MAXLV = EnhanceConfig.MAX_LEVEL

    def _stages(self):
        return [
            ec.growth_stage(lv, self.MAXLV, self.THRESHOLD)
            for lv in range(self.THRESHOLD, self.MAXLV + 1)
        ]

    def test_every_stage_is_actually_used(self):
        """안 쓰이는 단계는 그려 놓고 못 보는 그림 200장이다"""
        assert set(self._stages()) == set(ec.GROWTH_STAGES), (
            f"쓰이지 않는 단계가 있다: {sorted(set(ec.GROWTH_STAGES) - set(self._stages()))}"
        )

    def test_no_stage_hogs_or_starves(self):
        """예전엔 1단계가 Lv.10 하나뿐이었다. 한 레벨짜리 단계는 사고다"""
        counts = Counter(self._stages())
        span = self.MAXLV - self.THRESHOLD + 1
        even = span / len(ec.GROWTH_STAGES)
        for stage, n in counts.items():
            assert abs(n - even) <= 1, (
                f"{stage}단계가 {n}개 레벨 (고르면 {even:.1f}개): {dict(counts)}"
            )

    def test_stage_never_decreases(self):
        prev = 0
        for lv in range(0, self.MAXLV + 1):
            stage = ec.growth_stage(lv, self.MAXLV, self.THRESHOLD)
            assert stage >= prev, f"Lv.{lv}에서 단계가 내려갔다"
            prev = stage

    def test_art_starts_at_the_job_level(self):
        """직군 그림은 직군을 받는 레벨부터다. 그전을 나눠 쓰면 앞단계가 사장된다"""
        assert ec.growth_stage(self.THRESHOLD, self.MAXLV, self.THRESHOLD) == 1
        assert ec.growth_stage(self.MAXLV, self.MAXLV, self.THRESHOLD) == len(
            ec.GROWTH_STAGES
        )

    def test_stage_is_capped_above_max(self):
        """레벨이 만렙을 넘겨도 없는 단계를 가리키면 안 된다"""
        assert ec.growth_stage(999, self.MAXLV, self.THRESHOLD) == len(ec.GROWTH_STAGES)


class TestNoviceStage:
    """직군 배정 전 구간"""

    THRESHOLD = EnhanceConfig.CLASS_LEVEL_THRESHOLD

    def test_every_pre_job_level_has_an_image(self):
        """초반 열 레벨이 그림 없이 지나가면 각성이 뭘 주는지 안 보인다"""
        for lv in range(0, self.THRESHOLD):
            stage = ec.novice_stage(lv, self.THRESHOLD)
            assert ec.novice_art_stem(stage), f"Lv.{lv}에 그림이 없다"

    def test_every_novice_stage_is_used(self):
        stages = {ec.novice_stage(lv, self.THRESHOLD) for lv in range(self.THRESHOLD)}
        assert stages == set(ea.NOVICE_ART)

    def test_novice_stage_never_decreases(self):
        prev = 0
        for lv in range(0, self.THRESHOLD):
            stage = ec.novice_stage(lv, self.THRESHOLD)
            assert stage >= prev, f"Lv.{lv}에서 단계가 내려갔다"
            prev = stage

    def test_novice_art_does_not_collide_with_job_art(self):
        """쪼렙 그림이 직군 좌표를 쓰면 도감 칸 하나를 몰래 덮는다"""
        assert ea.NOVICE_KEY not in ea.CLASS_ART
        assert ea.NOVICE_RARITY not in ea.RARITY_ART


class TestRarityOdds:
    """종 확률과 보정"""

    def test_probabilities_sum_to_one(self):
        total = sum(p for p, _ in ec.RARITY_ODDS.values())
        assert total == pytest.approx(1.0), f"확률 합이 {total}"

    def test_rarer_is_less_likely(self):
        """노멀이 가장 두껍고 신화로 갈수록 얇아져야 한다"""
        order = ["normal", "rare", "epic", "legend", "myth"]
        probs = [ec.RARITY_ODDS[r][0] for r in order]
        for i in range(1, len(probs)):
            assert probs[i] < probs[i - 1], f"{order[i]}가 {order[i - 1]}보다 흔하다"

    def test_rarer_gives_more_bonus(self):
        order = ["normal", "rare", "epic", "legend", "myth"]
        bonuses = [ec.rarity_bonus(r) for r in order]
        for i in range(1, len(bonuses)):
            assert bonuses[i] > bonuses[i - 1]

    def test_bonus_is_capped_at_ten_percent(self):
        """보정이 이보다 커지면 종 하나가 매매 실력을 덮어버린다"""
        worst = max(ec.rarity_bonus(r) for r in ec.RARITY_ODDS)
        assert worst <= 10.0, f"최대 보정 {worst}%"

    def test_every_rarity_has_odds(self):
        assert set(ec.RARITY_ODDS) == set(RARITY_ART)

    def test_reroll_levels_are_within_range(self):
        """종 재추첨 지점이 도달 불가능한 레벨이면 아무 의미가 없다"""
        for lv in ec.RARITY_REROLL_LEVELS:
            assert 0 < lv <= EnhanceConfig.MAX_LEVEL, f"Lv.{lv}는 만렙을 넘는다"


class TestLabels:
    """표기 헬퍼가 enhance_art를 단일 출처로 쓰는지"""

    def test_class_label_uses_art_data(self):
        assert ec.class_label("scalper") == "⚡ 스캘퍼"

    def test_rarity_label_uses_art_data(self):
        assert ec.rarity_label("myth") == "🟨 신화"

    def test_family_lookup(self):
        assert ec.class_family("scalper") == ("트레이더", "⚡")

    def test_classes_of_family(self):
        assert len(ec.classes_of("trader")) == 5
        assert (
            sum(len(ec.classes_of(f)) for f in {v[0] for v in CLASS_ART.values()}) == 40
        )
