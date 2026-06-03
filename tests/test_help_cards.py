"""
도움말 카드 캐러셀 테스트
- 긴 simpleText 잘림 문제 해결을 위해 카테고리별 basicCard 캐러셀로 전환
- 모든 카드 버튼이 실제 라우팅되는 명령어를 가리켜 사용 흐름이 끊기지 않는지 검증
"""
from config import Messages
from handlers.command_handler import CommandHandler


def _make_handler():
    # handle_help는 db를 사용하지 않으므로 가벼운 인스턴스로 충분하다
    return CommandHandler(db=None, kakao_id="test", utterance="/도움말")


def test_help_returns_basiccard_carousel():
    """도움말은 basicCard 캐러셀로 응답한다"""
    resp = _make_handler().handle_help()
    outputs = resp["template"]["outputs"]
    assert len(outputs) == 1
    carousel = outputs[0]["carousel"]
    assert carousel["type"] == "basicCard"
    # 카드 수는 설정과 일치
    assert len(carousel["items"]) == len(Messages.HELP_CARDS)


def test_help_cards_have_title_description_buttons():
    """각 카드는 제목·본문·버튼을 갖고 버튼은 최대 3개 (카카오 제한)"""
    carousel = _make_handler().handle_help()["template"]["outputs"][0]["carousel"]
    for card in carousel["items"]:
        assert card["title"]
        assert card["description"]
        assert 1 <= len(card["buttons"]) <= 3


def test_help_card_descriptions_not_truncated():
    """카드 본문은 단말 잘림 방지를 위해 카드당 약 350자 이내로 유지한다"""
    for card in Messages.HELP_CARDS:
        assert len(card["description"]) <= 350, f"카드 본문이 너무 김: {card['title']}"


def test_every_help_button_routes_to_handler():
    """모든 카드 버튼은 실제 핸들러로 라우팅되어 흐름이 끊기지 않는다"""
    handler = _make_handler()
    carousel = handler.handle_help()["template"]["outputs"][0]["carousel"]
    for card in carousel["items"]:
        for btn in card["buttons"]:
            assert btn["action"] == "message"
            cmd = btn["messageText"]
            resolved = handler._find_handler(cmd.strip())
            assert resolved is not None, f"라우팅 없는 버튼: {cmd}"
            assert hasattr(CommandHandler, resolved), f"핸들러 없음: {resolved}"


def test_help_command_routes_to_handle_help():
    """'/도움말' 및 prefix 매칭('/도움말주식')이 handle_help로 라우팅된다"""
    handler = _make_handler()
    assert handler._find_handler("/도움말") == "handle_help"
    assert handler._find_handler("/도움말주식") == "handle_help"
