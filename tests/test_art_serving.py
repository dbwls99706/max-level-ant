"""
각성 직군 이미지 서빙 테스트

카카오 카드는 이미지를 공개 HTTPS 절대 URL로만 받는다. URL 조립이나
파일명 규칙이 어긋나면 카드가 통째로 렌더되지 않는데, 그건 서버 로그에
아무것도 남기지 않고 사용자 화면에서만 깨진다. 그래서 여기서 검증한다.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from enhance_art import all_combinations, image_stem
from settings import AssetConfig

ART_DIR = Path(AssetConfig.DIRECTORY)


class TestImageFiles:
    """저장소에 실제 이미지가 다 있는지"""

    def test_every_combination_has_an_image(self):
        """600개 조합 전부에 파일이 있어야 한다.

        직군을 추가하거나 이름을 바꾸면 이미지가 없는 조합이 생기는데,
        그 조합을 뽑은 유저에게만 카드가 깨져 보여서 발견이 늦다.
        """
        if not ART_DIR.is_dir():
            pytest.skip(f"{ART_DIR} 없음 - 이미지 생성 전")

        missing = [
            image_stem(*combo)
            for combo in all_combinations()
            if not (ART_DIR / f"{image_stem(*combo)}.webp").exists()
        ]
        assert not missing, f"이미지 없는 조합 {len(missing)}개: {missing[:10]}"

    def test_no_orphan_images(self):
        """조합에 없는 이미지가 남아 있지 않아야 한다 (직군 이름 변경 흔적)"""
        if not ART_DIR.is_dir():
            pytest.skip(f"{ART_DIR} 없음 - 이미지 생성 전")

        expected = {image_stem(*combo) for combo in all_combinations()}
        orphans = [p.stem for p in ART_DIR.glob("*.webp") if p.stem not in expected]
        assert not orphans, f"쓰이지 않는 이미지 {len(orphans)}개: {orphans[:10]}"


class TestImageUrl:
    """URL 조립"""

    def test_url_is_absolute_https(self, monkeypatch):
        monkeypatch.setattr(AssetConfig, "BASE_URL", "https://example.com")
        url = AssetConfig.image_url(image_stem("scalper", "myth", 3))
        assert url == "https://example.com/art/scalper__myth__g3.webp"

    def test_trailing_slash_does_not_double(self, monkeypatch):
        """BASE_URL 끝에 슬래시가 있어도 // 가 생기면 안 된다.

        환경변수에 슬래시를 붙여 넣기 쉬운데, 카카오는 그 URL을 그대로
        받아 이미지를 못 찾고 카드를 통째로 버린다.
        """
        monkeypatch.setattr(AssetConfig, "BASE_URL", "https://example.com/")
        assert AssetConfig.image_url("x") == "https://example.com/art/x.webp"

    def test_missing_base_url_returns_empty(self, monkeypatch):
        """미설정이면 예외가 아니라 빈 문자열 - 텍스트로 물러설 수 있어야 한다"""
        monkeypatch.setattr(AssetConfig, "BASE_URL", "")
        assert AssetConfig.image_url("x") == ""


class TestArtRoute:
    """/art 정적 라우트"""

    @pytest.fixture
    def client(self):
        from main import app

        return TestClient(app)

    def test_serves_an_existing_image(self, client):
        if not ART_DIR.is_dir():
            pytest.skip(f"{ART_DIR} 없음 - 이미지 생성 전")

        stem = image_stem("scalper", "normal", 1)
        resp = client.get(f"/art/{stem}.webp")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/webp"
        assert resp.content[:4] == b"RIFF", "WebP 파일이 아니다"

    def test_sets_long_cache_header(self, client):
        """무료 인스턴스가 이미지 재전송에 시간을 쓰지 않도록"""
        if not ART_DIR.is_dir():
            pytest.skip(f"{ART_DIR} 없음 - 이미지 생성 전")

        resp = client.get(f"/art/{image_stem('scalper', 'normal', 1)}.webp")
        cache = resp.headers.get("cache-control", "")
        assert "immutable" in cache
        assert f"max-age={AssetConfig.CACHE_MAX_AGE}" in cache

    def test_unknown_image_is_404(self, client):
        if not ART_DIR.is_dir():
            pytest.skip(f"{ART_DIR} 없음 - 이미지 생성 전")

        assert client.get("/art/nope__nope__g9.webp").status_code == 404

    def test_does_not_escape_the_directory(self, client):
        """상위 경로 탈출로 서버 파일을 읽을 수 없어야 한다"""
        if not ART_DIR.is_dir():
            pytest.skip(f"{ART_DIR} 없음 - 이미지 생성 전")

        for path in ("/art/../settings.py", "/art/..%2Fsettings.py"):
            resp = client.get(path)
            assert resp.status_code in (400, 403, 404), f"{path} 가 열렸다"
            assert b"DATABASE_URL" not in resp.content
