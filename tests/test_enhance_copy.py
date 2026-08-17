"""각성 화면 문구 규칙

이모티콘과 스포일러는 지우기는 쉽고 되살아나기도 쉽다. 다음에 문구를
손볼 때 조용히 되돌아오지 않도록 규칙을 여기 못박는다.
"""

import unicodedata
from unittest.mock import patch

import pytest

import enhance_classes as ec
from enhance_config import EnhanceConfig
from handlers.command_handler import CommandHandler
from services.collection_service import CollectionService
from settings import AssetConfig

THRESHOLD = EnhanceConfig.CLASS_LEVEL_THRESHOLD


def _emoji_count(text: str) -> int:
    """그림문자 개수. 진행 바(▓░▰▱)와 화살표는 정보라 세지 않는다."""
    skip = set("▓░▰▱→←↑↓")
    return sum(
        1
        for ch in text
        if ch not in skip
        and ord(ch) > 0x2000
        and unicodedata.category(ch) in ("So", "Sk")
    )


def _texts(resp: dict):
    """응답에서 사람이 읽는 문자열 전부"""
    out = []
    for output in resp["template"]["outputs"]:
        for kind, body in output.items():
            if kind == "simpleText":
                out.append(body["text"])
                continue
            for key in ("title", "description"):
                if body.get(key):
                    out.append(body[key])
    return out


def _run(db, user, utterance: str) -> dict:
    return CommandHandler(db, user.kakao_id, utterance, "테스터", "").handle()


def _always_succeed():
    return patch("services.enhance_service.random.randint", return_value=1)


def _always_fail():
    return patch("services.enhance_service.random.randint", return_value=100)


class TestNoSpoiler:
    """성공하기 전에 결과를 먼저 보여주면 누를 이유가 없다"""

    def test_info_does_not_reveal_the_next_title(self, db, test_user):
        test_user.enhance_level = 3
        test_user.cash = 100_000_000
        db.commit()

        info = EnhanceConfig.get_title(4, seed=0)
        with patch.object(EnhanceConfig, "get_title", return_value=info):
            body = "\n".join(_texts(_run(db, test_user, "/각성")))

        assert "성공 시" not in body, f"다음 칭호를 미리 보여준다:\n{body}"

    def test_info_does_not_shout_about_the_reset(self, db, test_user):
        """레벨 변화는 실패 화면의 'Lv.7 → Lv.0' 한 줄이 이미 말한다"""
        test_user.enhance_level = 7
        test_user.cash = 100_000_000
        db.commit()

        body = "\n".join(_texts(_run(db, test_user, "/각성")))
        assert "초기화" not in body, f"초기화 경고 줄이 살아 있다:\n{body}"
        assert "증발" not in body


class TestEmojiRestraint:
    """문구로 넘길 수 있는 자리에 이모티콘을 붙이지 않는다"""

    # 한 화면(말풍선 하나)에 허용할 개수.
    # 정체성 표기(칭호·계열·직군·종)만으로도 서너 개는 나오므로 그만큼 남긴다.
    MAX_PER_BUBBLE = 6

    def _assert_restrained(self, resp, where: str):
        for text in _texts(resp):
            n = _emoji_count(text)
            assert n <= self.MAX_PER_BUBBLE, f"{where}에 이모티콘 {n}개:\n{text}"

    def test_enhance_info(self, db, test_user):
        test_user.enhance_level = 12
        test_user.enhance_job = "scalper"
        test_user.enhance_rarity = "myth"
        test_user.cash = 100_000_000
        db.commit()
        self._assert_restrained(_run(db, test_user, "/각성"), "각성 정보")

    def test_enhance_success(self, db, test_user):
        test_user.enhance_level = THRESHOLD + 2
        test_user.enhance_job = "scalper"
        test_user.enhance_rarity = "myth"
        test_user.cash = 100_000_000
        db.commit()
        with _always_succeed():
            self._assert_restrained(_run(db, test_user, "/각성 시도"), "각성 성공")

    def test_enhance_failure(self, db, test_user):
        test_user.enhance_level = THRESHOLD + 5
        test_user.enhance_job = "scalper"
        test_user.enhance_rarity = "myth"
        test_user.cash = 100_000_000
        db.commit()
        with _always_fail():
            self._assert_restrained(_run(db, test_user, "/각성 시도"), "각성 실패")

    @pytest.mark.parametrize("command", ["/예측", "/보물상자"])
    def test_game_screens(self, db, test_user, command):
        test_user.cash = 100_000_000
        db.commit()
        self._assert_restrained(_run(db, test_user, command), command)


class TestButtonLabels:
    """버튼 이모티콘은 방향(급등·급락, 상승·하락)에만 남긴다"""

    DIRECTIONAL = ("급등", "급락", "상승", "하락")

    def _labels(self, resp):
        out = []
        for output in resp["template"]["outputs"]:
            for body in output.values():
                for btn in body.get("buttons", []) or []:
                    out.append(btn["label"])
        return out

    @pytest.mark.parametrize("command", ["/각성", "/예측", "/보물상자"])
    def test_only_directional_labels_keep_emoji(self, db, test_user, command):
        test_user.cash = 100_000_000
        db.commit()

        for label in self._labels(_run(db, test_user, command)):
            if any(word in label for word in self.DIRECTIONAL):
                continue
            assert _emoji_count(label) == 0, f"장식용 이모티콘이 남았다: {label!r}"


class TestBetLabelsAreHonest:
    """'올인'은 전 재산을 건다는 뜻이다. 2배 베팅은 올인이 아니다"""

    def test_no_all_in_label_for_a_doubling_bet(self):
        import inspect

        from handlers import base_handler, game_handler

        for module in (base_handler, game_handler):
            source = inspect.getsource(module)
            assert '"label": "2배 올인!"' not in source
            assert '"label": "🔥 2배 올인!"' not in source


class TestCardTellsWhatHappened:
    """카드만 봐도 이번에 무슨 일이 있었는지 알아야 한다.

    이미지 카드는 텍스트 경로와 본문이 다르다. 텍스트에는 있는데 카드에는
    없으면, 실제 유저가 보는 화면(카드)에서만 조용히 사라진다.
    """

    def _card(self, db, user, roll=1):
        with (
            patch.object(AssetConfig, "BASE_URL", "https://example.com"),
            patch("services.enhance_service.random.randint", return_value=roll),
        ):
            resp = _run(db, user, "/각성 시도")
        return resp["template"]["outputs"][0]["basicCard"]

    def test_failure_card_never_shows_none(self, db, test_user):
        """실패하면 직군·종이 풀린다. 성공용 본문을 쓰면 'None'이 찍힌다"""
        test_user.enhance_level = THRESHOLD + 18
        test_user.enhance_job = "scalper"
        test_user.enhance_rarity = "myth"
        test_user.cash = 100_000_000
        db.commit()

        card = self._card(db, test_user, roll=100)
        blob = f"{card['title']}\n{card['description']}"
        assert "None" not in blob, f"빈 값이 그대로 노출됐다:\n{blob}"

    def test_failure_card_names_what_was_lost(self, db, test_user):
        """가장 큰 사건이다. 잃은 이름을 말해줘야 사건이 된다"""
        test_user.enhance_level = THRESHOLD + 18
        test_user.enhance_job = "scalper"
        test_user.enhance_rarity = "myth"
        test_user.cash = 100_000_000
        db.commit()

        card = self._card(db, test_user, roll=100)
        blob = f"{card['title']}\n{card['description']}"
        assert "잃은 것" in blob, f"무엇을 잃었는지 없다:\n{blob}"
        assert "도감" in blob, "판을 넘어 남는 게 있다는 걸 알려줘야 한다"
        assert f"Lv.{THRESHOLD + 18}" in blob, "어디서 떨어졌는지 없다"

    def test_max_level_card_announces_it(self, db, test_user):
        """게임 최종 목표인데 평범한 레벨업과 같은 카드로 나가면 안 된다"""
        test_user.enhance_level = EnhanceConfig.MAX_LEVEL - 1
        test_user.enhance_job = "scalper"
        test_user.enhance_rarity = "myth"
        test_user.cash = 100_000_000
        db.commit()

        card = self._card(db, test_user)
        assert "만렙" in card["description"], f"만렙 표시가 없다:\n{card}"

    def test_rarity_drop_shows_both_sides(self, db, test_user):
        """'종 하락'만 적으면 무엇을 잃었는지 보이지 않는다"""
        test_user.enhance_level = 19
        test_user.enhance_job = "scalper"
        test_user.enhance_rarity = "myth"
        test_user.cash = 100_000_000
        db.commit()

        with patch.object(CollectionService, "roll_rarity", return_value="normal"):
            card = self._card(db, test_user)

        desc = card["description"]
        assert "종 하락" in desc, desc
        assert ec.rarity_label("myth") in desc, f"잃은 종이 안 보인다:\n{desc}"
        assert ec.rarity_label("normal") in desc

    def test_job_assignment_names_the_family(self, db, test_user):
        """판의 정체성이 정해지는 순간이다. 한 줄로 넘길 자리가 아니다"""
        test_user.enhance_level = THRESHOLD - 1
        test_user.cash = 100_000_000
        db.commit()

        card = self._card(db, test_user)
        assert "직군 배정" in card["description"]
        assert "계열" in card["description"], f"계열이 없다:\n{card['description']}"
