"""
카드 렌더링 불변식 테스트.

만렙개미 그룹 챗봇은 모든 본문을 '단일 카드(textCard)'로만 노출한다.
- 본문이 길어도 simpleText로 쪼개지지 않는다(본문/카드 분리 금지).
- 카드 본문은 항상 CARD_DESC_LIMIT 이하로 유지된다.
- 가변 목록은 fit_items()로 헤더·푸터를 보존하며 줄여 담는다.
"""
from utils import KakaoResponse

LIMIT = KakaoResponse.CARD_DESC_LIMIT


def _outputs(resp):
    return resp["template"]["outputs"]


class TestSingleCardInvariant:
    """text_with_buttons는 항상 textCard 하나만 반환한다."""

    def test_short_text_is_single_textcard(self):
        resp = KakaoResponse.text_with_buttons(
            "안녕하세요", [{"label": "A", "action": "message", "messageText": "/a"}]
        )
        outs = _outputs(resp)
        assert len(outs) == 1
        assert "textCard" in outs[0]
        assert "simpleText" not in outs[0]

    def test_very_long_text_never_splits(self):
        long_text = "\n".join(
            f"{i}. 어떤 종목 {i} 12,345원 (+1.2%) 🔺" for i in range(50)
        )
        resp = KakaoResponse.text_with_buttons(
            long_text, [{"label": "A", "action": "message", "messageText": "/a"}]
        )
        outs = _outputs(resp)
        # 단 하나의 textCard, simpleText 분리 절대 없음
        assert len(outs) == 1
        assert "textCard" in outs[0]
        assert "simpleText" not in outs[0]
        assert len(outs[0]["textCard"]["description"]) <= LIMIT

    def test_single_unbroken_long_line_is_trimmed(self):
        resp = KakaoResponse.text_with_buttons(
            "가" * 1000, [{"label": "A", "action": "message", "messageText": "/a"}]
        )
        outs = _outputs(resp)
        assert len(outs) == 1
        assert len(outs[0]["textCard"]["description"]) <= LIMIT

    def test_buttons_capped_at_five(self):
        btns = [
            {"label": f"B{i}", "action": "message", "messageText": f"/{i}"}
            for i in range(8)
        ]
        resp = KakaoResponse.text_with_buttons("hi", btns)
        assert len(_outputs(resp)[0]["textCard"]["buttons"]) == 5

    def test_no_buttons_is_single_bubble(self):
        resp = KakaoResponse.text_with_buttons("버튼 없음", [])
        assert len(_outputs(resp)) == 1


class TestFitItems:
    """fit_items: 헤더·푸터는 보존, 항목만 한도 내에서 줄이고 '…외 N개'를 붙인다."""

    def test_all_fit_returns_full_body(self):
        body = KakaoResponse.fit_items("헤더", ["a", "b", "c"], "푸터")
        assert body == "헤더\na\nb\nc\n푸터"

    def test_caps_items_and_appends_more(self):
        items = [f"항목{i} " + "가" * 30 for i in range(20)]
        body = KakaoResponse.fit_items(
            "📋 헤더", items, "요약 푸터", more_fmt="…외 {n}개 더"
        )
        assert len(body) <= LIMIT
        assert body.startswith("📋 헤더")
        assert body.endswith("요약 푸터")          # 푸터는 절대 누락 안 됨
        assert "…외" in body and "개 더" in body   # 생략 표시 존재

    def test_footer_preserved_even_when_items_are_huge(self):
        items = ["엄청 긴 항목 " + "가" * 200 for _ in range(5)]
        body = KakaoResponse.fit_items("H", items, "중요한 요약 푸터")
        assert body.endswith("중요한 요약 푸터")
        assert len(body) <= LIMIT

    def test_more_count_is_accurate(self):
        items = [f"x{i}" for i in range(10)]
        # 매우 작은 한도로 강제 — 헤더만 들어가고 전부 생략되는 상황
        body = KakaoResponse.fit_items("H", items, "", limit=12, more_fmt="외 {n}개")
        # 남은 개수 표기가 실제 드롭된 개수와 일치
        import re
        m = re.search(r"외 (\d+)개", body)
        assert m is not None
        dropped = int(m.group(1))
        shown = len([ln for ln in body.split("\n") if ln.startswith("x")])
        assert dropped == 10 - shown
