"""
각성 도감 - 배정·재추첨·기록·표시 테스트

도감은 "각성 실패로 전부 잃어도 남는 것"이라는 약속 위에 서 있다.
그 약속이 깨지면 유저는 다시 시작할 이유가 없어지는데, 깨져도 서버는
아무 소리도 내지 않는다. 그래서 경계마다 못을 박는다.
"""

import json
from unittest.mock import patch

import pytest

import enhance_classes as ec
from enhance_art import CLASS_ART, FAMILIES, RARITY_ART, all_combinations
from enhance_config import EnhanceConfig
from models import ClassCollection
from services.collection_service import CollectionService
from services.enhance_service import EnhanceService
from settings import AssetConfig

THRESHOLD = EnhanceConfig.CLASS_LEVEL_THRESHOLD


def _always_succeed():
    return patch("services.enhance_service.random.randint", return_value=1)


def _always_fail():
    return patch("services.enhance_service.random.randint", return_value=100)


class TestRolls:
    """추첨"""

    def test_roll_job_returns_a_real_job(self):
        for _ in range(200):
            assert CollectionService.roll_job() in CLASS_ART

    def test_roll_job_can_reach_every_job(self):
        """뽑히지 않는 직군이 있으면 그 도감 칸은 영영 안 열린다"""
        seen = {CollectionService.roll_job() for _ in range(4000)}
        missing = set(CLASS_ART) - seen
        assert not missing, f"4000번 뽑았는데 안 나온 직군: {missing}"

    def test_roll_rarity_follows_the_odds(self):
        """선언한 확률과 실제 추첨이 어긋나면 밸런스 계산이 전부 무의미해진다"""
        n = 40000
        counts = {r: 0 for r in RARITY_ART}
        for _ in range(n):
            counts[CollectionService.roll_rarity()] += 1

        for rarity, (expected, _bonus) in ec.RARITY_ODDS.items():
            actual = counts[rarity] / n
            assert abs(actual - expected) < max(0.01, expected * 0.15), (
                f"{rarity} 실제 {actual:.3%} vs 기대 {expected:.1%}"
            )

    def test_rarity_change_direction(self):
        assert CollectionService.rarity_changed("normal", "myth") == 1
        assert CollectionService.rarity_changed("myth", "normal") == -1
        assert CollectionService.rarity_changed("epic", "epic") == 0
        assert CollectionService.rarity_changed(None, "epic") == 0
        assert CollectionService.rarity_changed("없는등급", "epic") == 0


class TestUnlock:
    """도감 기록"""

    def test_unlock_records_once(self, db, test_user):
        assert CollectionService.unlock(db, test_user.kakao_id, "scalper", "myth", 3)
        db.commit()
        assert not CollectionService.unlock(
            db, test_user.kakao_id, "scalper", "myth", 3
        )
        assert (
            db.query(ClassCollection)
            .filter(ClassCollection.kakao_id == test_user.kakao_id)
            .count()
            == 1
        )

    def test_unlock_rejects_unknown_coordinates(self, db, test_user):
        assert not CollectionService.unlock(db, test_user.kakao_id, "nope", "myth", 1)
        assert not CollectionService.unlock(
            db, test_user.kakao_id, "scalper", "nope", 1
        )
        assert not CollectionService.unlock(
            db, test_user.kakao_id, "scalper", "myth", 9
        )

    def test_unlock_failure_does_not_roll_back_the_caller(self, db, test_user):
        """도감 기록이 유니크 제약에 걸려도 바깥 트랜잭션은 살아 있어야 한다.

        예전 구현은 IntegrityError에서 db.rollback()을 불렀다. 그러면
        같은 트랜잭션에 있던 레벨업과 비용 차감까지 통째로 사라진다.
        도감은 부가 기록이지 각성의 조건이 아니다.

        사전 검사(_already_unlocked)를 통과한 두 요청이 동시에 들어온
        상황을 재현해야 이 경로에 도달한다. 그래서 검사만 False로 만든다.
        """
        CollectionService.unlock(db, test_user.kakao_id, "scalper", "myth", 3)
        db.commit()

        test_user.cash = 12345
        test_user.nickname = "살아남아야_한다"

        with patch.object(CollectionService, "_already_unlocked", return_value=False):
            assert not CollectionService.unlock(
                db, test_user.kakao_id, "scalper", "myth", 3
            )

        db.commit()
        db.refresh(test_user)
        assert test_user.cash == 12345, "도감 기록 실패가 바깥 변경을 되돌렸다"
        assert test_user.nickname == "살아남아야_한다"
        assert (
            db.query(ClassCollection)
            .filter(ClassCollection.kakao_id == test_user.kakao_id)
            .count()
            == 1
        ), "중복 행이 들어갔다"


class TestJobAssignment:
    """직군·종 배정"""

    def test_no_job_below_threshold(self, db, test_user):
        test_user.enhance_level = THRESHOLD - 2
        test_user.cash = 100_000_000
        db.commit()

        with _always_succeed():
            result = EnhanceService.attempt_enhance(db, test_user.kakao_id)

        assert result["new_level"] == THRESHOLD - 1
        assert result["job"] is None
        # 직군은 없어도 그림은 있어야 한다. 초반 열 레벨이 텍스트만 나오면
        # 각성이 무엇을 주는 시스템인지 보이지 않는다.
        assert result["art_stem"] is not None, "쪼렙 구간에 그림이 없다"
        assert result["art_stem"].startswith("novice__"), (
            f"직군이 없는데 직군 그림이 붙었다: {result['art_stem']}"
        )

    def test_job_assigned_at_threshold(self, db, test_user):
        test_user.enhance_level = THRESHOLD - 1
        test_user.cash = 100_000_000
        db.commit()

        with _always_succeed():
            result = EnhanceService.attempt_enhance(db, test_user.kakao_id)

        assert result["job_assigned"] is True
        assert result["job"] in CLASS_ART
        assert result["rarity"] in RARITY_ART
        assert result["art_stem"] is not None
        assert result["flavor"]

    def test_assignment_unlocks_the_collection(self, db, test_user):
        test_user.enhance_level = THRESHOLD - 1
        test_user.cash = 100_000_000
        db.commit()

        with _always_succeed():
            result = EnhanceService.attempt_enhance(db, test_user.kakao_id)

        entries = CollectionService.get_entries(db, test_user.kakao_id)
        assert len(entries) == 1
        e = entries[0]
        assert (e.job, e.rarity, e.growth) == (
            result["job"],
            result["rarity"],
            result["growth"],
        )
        assert result["newly_unlocked"] is True

    def test_job_is_kept_while_leveling(self, db, test_user):
        """레벨을 더 올려도 직군은 그대로여야 한다"""
        test_user.enhance_level = THRESHOLD
        test_user.enhance_job = "scalper"
        test_user.enhance_rarity = "epic"
        test_user.cash = 100_000_000
        db.commit()

        with _always_succeed():
            result = EnhanceService.attempt_enhance(db, test_user.kakao_id)

        assert result["job"] == "scalper"
        assert result["job_assigned"] is False


class TestRarityReroll:
    """종 재추첨"""

    @pytest.mark.parametrize("level", ec.RARITY_REROLL_LEVELS)
    def test_reroll_happens_at_designated_levels(self, db, test_user, level):
        if level - 1 < THRESHOLD:
            pytest.skip("직군 배정 레벨 이전에는 재추첨이 아니라 최초 배정이다")

        test_user.enhance_level = level - 1
        test_user.enhance_job = "scalper"
        test_user.enhance_rarity = "normal"
        test_user.cash = 100_000_000
        db.commit()

        with _always_succeed():
            result = EnhanceService.attempt_enhance(db, test_user.kakao_id)

        assert result["new_level"] == level
        assert result["rarity_rerolled"] is True

    def test_no_reroll_on_ordinary_levels(self, db, test_user):
        ordinary = next(
            lv
            for lv in range(THRESHOLD + 1, EnhanceConfig.MAX_LEVEL)
            if lv not in ec.RARITY_REROLL_LEVELS
        )
        test_user.enhance_level = ordinary - 1
        test_user.enhance_job = "scalper"
        test_user.enhance_rarity = "normal"
        test_user.cash = 100_000_000
        db.commit()

        with _always_succeed():
            result = EnhanceService.attempt_enhance(db, test_user.kakao_id)

        assert result["rarity_rerolled"] is False
        assert result["rarity"] == "normal", "재추첨 레벨이 아닌데 종이 바뀌었다"

    def test_reroll_reports_direction(self, db, test_user):
        level = 20
        test_user.enhance_level = level - 1
        test_user.enhance_job = "scalper"
        test_user.enhance_rarity = "normal"
        test_user.cash = 100_000_000
        db.commit()

        with (
            _always_succeed(),
            patch.object(CollectionService, "roll_rarity", return_value="myth"),
        ):
            result = EnhanceService.attempt_enhance(db, test_user.kakao_id)

        assert result["rarity"] == "myth"
        assert result["rarity_delta"] == 1
        assert result["old_rarity"] == "normal"


class TestGrowthTransition:
    """성장 단계가 바뀌면 그림도 바뀐다"""

    def test_growth_change_is_reported(self, db, test_user):
        boundary = next(
            lv
            for lv in range(THRESHOLD + 1, EnhanceConfig.MAX_LEVEL + 1)
            if ec.growth_stage(lv, EnhanceConfig.MAX_LEVEL, THRESHOLD)
            != ec.growth_stage(lv - 1, EnhanceConfig.MAX_LEVEL, THRESHOLD)
        )
        test_user.enhance_level = boundary - 1
        test_user.enhance_job = "scalper"
        test_user.enhance_rarity = "normal"
        test_user.cash = 100_000_000
        db.commit()

        with _always_succeed():
            result = EnhanceService.attempt_enhance(db, test_user.kakao_id)

        assert result["growth_changed"] is True
        assert result["art_stem"].endswith(f"g{result['growth']}")

    def test_growth_change_is_not_reported_within_a_stage(self, db, test_user):
        """단계 안에서 레벨만 오르면 그림이 그대로다. '단계 진입'은 거짓말이다"""
        inside = next(
            lv
            for lv in range(THRESHOLD + 1, EnhanceConfig.MAX_LEVEL)
            if ec.growth_stage(lv, EnhanceConfig.MAX_LEVEL, THRESHOLD)
            == ec.growth_stage(lv - 1, EnhanceConfig.MAX_LEVEL, THRESHOLD)
        )
        test_user.enhance_level = inside - 1
        test_user.enhance_job = "scalper"
        test_user.enhance_rarity = "normal"
        test_user.cash = 100_000_000
        db.commit()

        with _always_succeed():
            result = EnhanceService.attempt_enhance(db, test_user.kakao_id)

        assert result["growth_changed"] is False, (
            f"Lv.{inside - 1}→{inside}은 같은 단계인데 진입이라고 한다"
        )

    def test_growth_transition_unlocks_a_new_entry(self, db, test_user):
        """같은 직군·종이라도 성장이 바뀌면 새 칸이다"""
        boundary = next(
            lv
            for lv in range(THRESHOLD + 1, EnhanceConfig.MAX_LEVEL + 1)
            if ec.growth_stage(lv, EnhanceConfig.MAX_LEVEL, THRESHOLD) == 2
        )
        test_user.enhance_level = boundary - 1
        test_user.enhance_job = "scalper"
        test_user.enhance_rarity = "normal"
        test_user.cash = 100_000_000
        db.add(
            ClassCollection(
                kakao_id=test_user.kakao_id, job="scalper", rarity="normal", growth=1
            )
        )
        db.commit()

        with _always_succeed():
            result = EnhanceService.attempt_enhance(db, test_user.kakao_id)

        assert result["growth"] == 2
        assert result["newly_unlocked"] is True
        assert len(CollectionService.get_entries(db, test_user.kakao_id)) == 2


class TestSummary:
    """도감 진행도 집계"""

    def test_empty_summary(self, db, test_user):
        s = CollectionService.get_summary(db, test_user.kakao_id)
        assert s["owned"] == 0
        assert s["total"] == len(CLASS_ART) * len(RARITY_ART) * len(ec.GROWTH_STAGES)
        assert s["percent"] == 0.0
        assert s["jobs_owned"] == 0

    def test_total_is_derived_not_hardcoded(self, db, test_user):
        """직군을 늘렸을 때 영영 100%가 안 되는 도감이 되면 안 된다"""
        s = CollectionService.get_summary(db, test_user.kakao_id)
        assert s["total"] == len(list(all_combinations()))

    def test_full_collection_is_hundred_percent(self, db, test_user):
        for job, rarity, growth in all_combinations():
            db.add(
                ClassCollection(
                    kakao_id=test_user.kakao_id,
                    job=job,
                    rarity=rarity,
                    growth=growth,
                )
            )
        db.commit()

        s = CollectionService.get_summary(db, test_user.kakao_id)
        assert s["owned"] == s["total"]
        assert s["percent"] == 100.0
        assert s["jobs_owned"] == len(CLASS_ART)
        for family in FAMILIES:
            f = s["by_family"][family]
            assert f["owned"] == f["total"]

    def test_stale_entries_are_ignored(self, db, test_user):
        """직군을 삭제했을 때 옛 기록이 진행도를 100% 넘기면 안 된다"""
        db.add(
            ClassCollection(
                kakao_id=test_user.kakao_id,
                job="사라진직군",
                rarity="myth",
                growth=1,
            )
        )
        db.commit()

        s = CollectionService.get_summary(db, test_user.kakao_id)
        assert s["owned"] == 0
        assert s["percent"] == 0.0

    def test_family_detail_lists_every_job(self, db, test_user):
        detail = CollectionService.get_family_detail(db, test_user.kakao_id, "trader")
        assert len(detail["jobs"]) == len(ec.classes_of("trader"))
        assert all(j["owned"] == 0 and j["best_rarity"] is None for j in detail["jobs"])

    def test_family_detail_reports_best_rarity(self, db, test_user):
        for rarity in ("normal", "epic"):
            db.add(
                ClassCollection(
                    kakao_id=test_user.kakao_id,
                    job="scalper",
                    rarity=rarity,
                    growth=1,
                )
            )
        db.commit()

        detail = CollectionService.get_family_detail(db, test_user.kakao_id, "trader")
        scalper = next(j for j in detail["jobs"] if j["job"] == "scalper")
        assert scalper["owned"] == 2
        assert scalper["best_rarity"] == "epic", "더 높은 종을 최고로 잡아야 한다"


class TestRankingBonus:
    """종 보정이 랭킹에만 반영되는지"""

    def test_bonus_is_added_to_ranking_rate(self, db, test_user):
        from services.ranking_service import RankingService

        test_user.enhance_rarity = "myth"
        db.commit()
        RankingService._ranking_cache.clear()

        rankings = RankingService._build_rankings(db)
        me = next(r for r in rankings if r["kakao_id"] == test_user.kakao_id)
        assert me["rarity_bonus"] == ec.rarity_bonus("myth")
        assert me["profit_rate"] == round(me["raw_profit_rate"] + me["rarity_bonus"], 2)

    def test_no_rarity_means_no_bonus(self, db, test_user):
        from services.ranking_service import RankingService

        test_user.enhance_rarity = None
        db.commit()
        RankingService._ranking_cache.clear()

        rankings = RankingService._build_rankings(db)
        me = next(r for r in rankings if r["kakao_id"] == test_user.kakao_id)
        assert me["rarity_bonus"] == 0.0
        assert me["profit_rate"] == me["raw_profit_rate"]

    def test_bonus_changes_the_order(self, db, test_user, rich_user):
        """보정이 순위를 실제로 바꿔야 의미가 있다"""
        from services.ranking_service import RankingService

        # 두 유저의 원래 수익률을 같게 맞춘다
        for u in (test_user, rich_user):
            u.cash = 10_000_000
            u.initial_cash = 10_000_000
            u.enhance_rarity = None
        db.commit()
        RankingService._ranking_cache.clear()
        before = [r["kakao_id"] for r in RankingService._build_rankings(db)]

        rich_user.enhance_rarity = "myth"
        db.commit()
        RankingService._ranking_cache.clear()
        after = [r["kakao_id"] for r in RankingService._build_rankings(db)]

        assert after[0] == rich_user.kakao_id, "신화를 뽑았는데 순위가 안 올랐다"
        assert before != after or len(before) == 1

    def test_balance_view_stays_raw(self, db, test_user):
        """잔고 화면의 수익률에는 보정을 얹지 않는다"""
        from services.ranking_service import RankingService

        test_user.enhance_rarity = "myth"
        test_user.cash = 10_000_000
        test_user.initial_cash = 10_000_000
        db.commit()

        _asset, rate = RankingService.calculate_total_asset(db, test_user)
        assert rate == 0.0, "잔고 수익률에 랭킹 보정이 섞였다"


class TestCollectionCommand:
    """/도감 응답"""

    def _handle(self, db, user, utterance):
        from handlers import CommandHandler

        return CommandHandler(db, user.kakao_id, utterance, "테스터", "").handle()

    def test_summary_renders(self, db, test_user):
        from tests.test_kakao_spec_compliance import assert_valid_skill_response

        resp = self._handle(db, test_user, "/도감")
        assert_valid_skill_response(resp, "/도감")
        text = json.dumps(resp, ensure_ascii=False)
        assert "도감" in text
        assert f"/{len(list(all_combinations()))}" in text

    def test_family_detail_renders(self, db, test_user):
        from tests.test_kakao_spec_compliance import assert_valid_skill_response

        resp = self._handle(db, test_user, "/도감 트레이더")
        assert_valid_skill_response(resp, "/도감 트레이더")
        assert "트레이더" in json.dumps(resp, ensure_ascii=False)

    def test_every_family_name_is_accepted(self, db, test_user):
        """계열 이름 하나라도 못 알아들으면 그 계열은 볼 방법이 없다"""
        from tests.test_kakao_spec_compliance import assert_valid_skill_response

        for name, _emoji in FAMILIES.values():
            resp = self._handle(db, test_user, f"/도감 {name}")
            assert_valid_skill_response(resp, f"/도감 {name}")
            text = json.dumps(resp, ensure_ascii=False)
            assert "찾을 수 없습니다" not in text, f"{name} 계열을 못 알아들었다"

    def test_unknown_family_is_guided(self, db, test_user):
        from tests.test_kakao_spec_compliance import assert_valid_skill_response

        resp = self._handle(db, test_user, "/도감 없는계열")
        assert_valid_skill_response(resp, "/도감 없는계열")
        assert "찾을 수 없습니다" in json.dumps(resp, ensure_ascii=False)


class TestEnhanceCard:
    """각성 성공 시 이미지 카드"""

    def _enhance(self, db, user, base_url):
        from handlers import CommandHandler

        user.enhance_level = 12
        user.enhance_job = "scalper"
        user.enhance_rarity = "myth"
        user.cash = 100_000_000
        db.commit()

        with (
            patch("services.common.is_market_open", return_value=False),
            patch.object(AssetConfig, "BASE_URL", base_url),
            _always_succeed(),
        ):
            return CommandHandler(
                db, user.kakao_id, "/각성 시도", "테스터", ""
            ).handle()

    def test_card_shows_the_matching_image(self, db, test_user):
        from tests.test_kakao_spec_compliance import assert_valid_skill_response

        resp = self._enhance(db, test_user, "https://example.com")
        assert_valid_skill_response(resp, "각성 카드")

        card = resp["template"]["outputs"][0]["basicCard"]
        url = card["thumbnail"]["imageUrl"]
        assert url.startswith("https://example.com/art/")
        assert "scalper__myth__g" in url, "다른 조합의 이미지가 붙었다"

    def test_image_fills_the_card_width(self, db, test_user):
        """fixedRatio가 없으면 카카오가 잘라서 작은 썸네일로 띄운다"""
        resp = self._enhance(db, test_user, "https://example.com")
        thumb = resp["template"]["outputs"][0]["basicCard"]["thumbnail"]

        assert thumb.get("fixedRatio") is True, (
            "그림이 주인공인 카드인데 카카오 기본 비율로 잘리게 뒀다"
        )
        assert (thumb.get("width"), thumb.get("height")) == AssetConfig.image_size(), (
            f"원본 비율과 다른 크기: {thumb.get('width')}x{thumb.get('height')}"
        )

    def test_card_text_matches_the_image(self, db, test_user):
        resp = self._enhance(db, test_user, "https://example.com")
        card = resp["template"]["outputs"][0]["basicCard"]

        stem = card["thumbnail"]["imageUrl"].rsplit("/", 1)[-1].removesuffix(".webp")
        job, rarity, growth_raw = stem.split("__")
        expected = ec.awakening_flavor(job, rarity, int(growth_raw[1:]))

        # 카드 설명은 230자로 잘리므로 첫 줄만 비교한다
        assert expected.split("\n")[0] in card["description"]
        assert ec.rarity_label(rarity) in card["description"]

    def test_falls_back_to_text_without_base_url(self, db, test_user):
        """PUBLIC_BASE_URL이 없으면 카드 대신 텍스트로 나가야 한다"""
        from tests.test_kakao_spec_compliance import assert_valid_skill_response

        resp = self._enhance(db, test_user, "")
        assert_valid_skill_response(resp, "각성 텍스트 폴백")
        kind = next(iter(resp["template"]["outputs"][0]))
        assert kind != "basicCard", "이미지 URL이 없는데 카드를 만들었다"
