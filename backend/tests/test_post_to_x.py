"""X 게시 스크립트(scripts/post_to_x.py)의 서명·글자 수 계약 테스트.

서명은 X 공식 문서의 'Creating a signature' 예시(고정 nonce·timestamp)와 한 비트도 달라서는 안 된다.
틀리면 실제 게시 때 401로만 보이고 원인을 짚기 어렵다. 네트워크는 쓰지 않는다.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from urllib.parse import unquote

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "post_to_x.py"


@pytest.fixture(scope="module")
def post_to_x():
    spec = importlib.util.spec_from_file_location("post_to_x", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(spec.name, None)


def test_oauth_signature_matches_documented_example(post_to_x):
    header = post_to_x.oauth_header(
        "POST",
        "https://api.twitter.com/1.1/statuses/update.json",
        api_key="xvz1evFS4wEEPTGEFPHBog",
        api_secret="kAcSOqF21Fu85e7zjz7ZN2U4ZRhfV3WpwPAoE3Z7kBw",
        access_token="370773112-GmHxMAgYyLbNEtIKZeRNFsMKPR9EyMZeS9weJAEb",
        access_token_secret="LswwdoUaIvS8ltyTt5jkRh4J50vUPVVHtR2YPi5kE",
        extra_params={
            "include_entities": "true",
            "status": "Hello Ladies + Gentlemen, a signed OAuth request!",
        },
        nonce="kYjzVBB8Y0ZFabxSWbWovY3uYSQ2pTgmZeNu2VS4cg",
        timestamp="1318622958",
    )
    signature = unquote(header.split('oauth_signature="')[1].split('"')[0])
    assert signature == "hCtSmYh+iHYCEqBWrE7C7hYmtUk="


def test_header_never_contains_secrets(post_to_x):
    header = post_to_x.oauth_header(
        "POST",
        post_to_x.TWEETS_URL,
        api_key="KEY",
        api_secret="API-SECRET-VALUE",
        access_token="TOKEN",
        access_token_secret="TOKEN-SECRET-VALUE",
    )
    assert "API-SECRET-VALUE" not in header
    assert "TOKEN-SECRET-VALUE" not in header
    assert header.startswith("OAuth ")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("hello", 5),          # 영문·숫자·공백 = 1
        ("널스탁", 6),          # 한글 = 2
        ("CAGR 12.4%", 10),
        ("백테스트 결과", 13),   # 한글 6자×2 + 공백 1
    ],
)
def test_weighted_length(post_to_x, text, expected):
    assert post_to_x.weighted_length(text) == expected


def test_korean_post_limit_is_140_characters(post_to_x):
    assert post_to_x.weighted_length("가" * 140) == post_to_x.MAX_WEIGHTED_LENGTH
    assert post_to_x.weighted_length("가" * 141) > post_to_x.MAX_WEIGHTED_LENGTH


def test_dry_run_sends_nothing_and_needs_no_credentials(post_to_x, monkeypatch, capsys):
    for name in post_to_x.CREDENTIAL_ENV:
        monkeypatch.delenv(name, raising=False)

    def _boom(*args, **kwargs):
        raise AssertionError("미리보기에서 네트워크 호출이 일어났다")

    monkeypatch.setattr(post_to_x.requests, "post", _boom)
    monkeypatch.setattr(sys, "argv", ["post_to_x.py", "테스트 글"])
    post_to_x.main()
    assert "미리보기만" in capsys.readouterr().out


def test_missing_credentials_fail_fast_naming_only_variable_names(post_to_x, monkeypatch):
    for name in post_to_x.CREDENTIAL_ENV:
        monkeypatch.delenv(name, raising=False)
    # .env를 다시 읽어 들이지 않게 한다(실제 .env에 값이 있어도 테스트가 흔들리지 않도록)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    with pytest.raises(SystemExit) as exc:
        post_to_x.load_credentials()
    assert "X_ACCESS_TOKEN" in str(exc.value)


# ── 인용·답글·사진 ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "ref",
    [
        "2105200339469394331",
        "https://x.com/Jaemyung_Lee/status/2105200339469394331?s=20",
        "https://x.com/Jaemyung_Lee/status/2105200339469394331/",
    ],
)
def test_tweet_id_from_accepts_url_or_bare_id(post_to_x, ref):
    assert post_to_x.tweet_id_from(ref) == "2105200339469394331"


def test_tweet_id_from_rejects_non_numeric(post_to_x):
    with pytest.raises(SystemExit):
        post_to_x.tweet_id_from("https://x.com/Jaemyung_Lee")


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


_CREDS = {
    "api_key": "k", "api_secret": "s", "access_token": "t", "access_token_secret": "ts",
}


def test_post_tweet_builds_quote_reply_and_media_body(post_to_x, monkeypatch):
    sent = {}

    def _fake_post(url, **kwargs):
        sent["url"], sent["json"] = url, kwargs["json"]
        return _FakeResponse(201, {"data": {"id": "999"}})

    monkeypatch.setattr(post_to_x.requests, "post", _fake_post)
    tweet_id = post_to_x.post_tweet(
        "본문", _CREDS, quote_id="111", reply_to_id="222", media_ids=["m1", "m2"]
    )
    assert tweet_id == "999"
    assert sent["url"] == post_to_x.TWEETS_URL
    assert sent["json"] == {
        "text": "본문",
        "quote_tweet_id": "111",
        "reply": {"in_reply_to_tweet_id": "222"},
        "media": {"media_ids": ["m1", "m2"]},
    }


def test_post_tweet_plain_body_has_only_text(post_to_x, monkeypatch):
    sent = {}
    monkeypatch.setattr(
        post_to_x.requests, "post",
        lambda url, **kw: sent.update(json=kw["json"]) or _FakeResponse(201, {"data": {"id": "1"}}),
    )
    post_to_x.post_tweet("안녕", _CREDS)
    assert sent["json"] == {"text": "안녕"}


def test_upload_image_returns_media_id(post_to_x, monkeypatch, tmp_path):
    image = tmp_path / "a.png"
    image.write_bytes(b"\x89PNG")
    monkeypatch.setattr(
        post_to_x.requests, "post",
        lambda url, **kw: _FakeResponse(200, {"data": {"id": "777"}}),
    )
    assert post_to_x.upload_image(image, _CREDS) == "777"


def test_check_images_rejects_bad_inputs(post_to_x, tmp_path):
    good = tmp_path / "a.png"
    good.write_bytes(b"x")
    post_to_x.check_images([good])  # 통과
    with pytest.raises(SystemExit):
        post_to_x.check_images([tmp_path / "missing.png"])
    gif = tmp_path / "a.gif"
    gif.write_bytes(b"x")
    with pytest.raises(SystemExit):
        post_to_x.check_images([gif])
    with pytest.raises(SystemExit):
        post_to_x.check_images([good] * 5)
    big = tmp_path / "big.png"
    big.write_bytes(b"x" * (post_to_x.MAX_IMAGE_BYTES + 1))
    with pytest.raises(SystemExit):
        post_to_x.check_images([big])


def test_empty_reply_to_is_rejected_not_silently_dropped(post_to_x, monkeypatch):
    """앞 단계가 실패해 id가 빈 채 넘어오면 단독 글로 나가지 않고 중단해야 한다(2026-10-04 사고)."""
    def _boom(*args, **kwargs):
        raise AssertionError("네트워크 호출이 일어났다")

    monkeypatch.setattr(post_to_x.requests, "post", _boom)
    monkeypatch.setattr(sys, "argv", ["post_to_x.py", "글", "--reply-to", "", "--post"])
    with pytest.raises(SystemExit):
        post_to_x.main()


def test_long_flag_lifts_the_280_limit_only_when_given(post_to_x, monkeypatch, capsys):
    monkeypatch.setattr(post_to_x.requests, "post", lambda *a, **k: (_ for _ in ()).throw(AssertionError("전송됨")))
    long_text = "가" * 500  # 가중 1000 — 일반 한도(280) 초과, --long 한도(25000) 이내
    monkeypatch.setattr(sys, "argv", ["post_to_x.py", long_text])
    with pytest.raises(SystemExit):
        post_to_x.main()
    monkeypatch.setattr(sys, "argv", ["post_to_x.py", long_text, "--long"])
    post_to_x.main()
    assert "미리보기만" in capsys.readouterr().out


def test_check_video_rejects_bad_inputs(post_to_x, tmp_path):
    video = tmp_path / "a.mp4"
    video.write_bytes(b"x")
    post_to_x.check_video(video, [])  # 통과
    with pytest.raises(SystemExit):
        post_to_x.check_video(tmp_path / "missing.mp4", [])
    webm = tmp_path / "a.webm"
    webm.write_bytes(b"x")
    with pytest.raises(SystemExit):
        post_to_x.check_video(webm, [])
    with pytest.raises(SystemExit):  # X는 동영상과 사진을 한 글에 같이 받지 않는다
        post_to_x.check_video(video, [tmp_path / "a.png"])


def test_upload_video_chunks_then_waits_for_processing(post_to_x, monkeypatch, tmp_path):
    video = tmp_path / "a.mp4"
    video.write_bytes(b"v" * 10)
    monkeypatch.setattr(post_to_x, "VIDEO_CHUNK_BYTES", 4)  # 10바이트 → 조각 3개
    monkeypatch.setattr(post_to_x.time, "sleep", lambda _s: None)
    posts, gets = [], []

    def _fake_post(url, **kwargs):
        posts.append((url, kwargs.get("json"), kwargs.get("data")))
        if url.endswith("/initialize"):
            return _FakeResponse(200, {"data": {"id": "555"}})
        if url.endswith("/finalize"):
            return _FakeResponse(200, {"data": {"id": "555", "processing_info": {"state": "pending", "check_after_secs": 1}}})
        return _FakeResponse(204, {})

    def _fake_get(url, **kwargs):
        gets.append(kwargs["params"])
        state = "in_progress" if len(gets) == 1 else "succeeded"
        return _FakeResponse(200, {"data": {"id": "555", "processing_info": {"state": state}}})

    monkeypatch.setattr(post_to_x.requests, "post", _fake_post)
    monkeypatch.setattr(post_to_x.requests, "get", _fake_get)
    assert post_to_x.upload_video(video, _CREDS) == "555"
    assert posts[0][1] == {"media_type": "video/mp4", "total_bytes": 10, "media_category": "tweet_video"}
    assert [p[2]["segment_index"] for p in posts[1:4]] == ["0", "1", "2"]
    assert posts[4][0].endswith("/555/finalize")
    assert gets == [{"command": "STATUS", "media_id": "555"}] * 2


def test_upload_video_fails_fast_when_processing_fails(post_to_x, monkeypatch, tmp_path):
    video = tmp_path / "a.mp4"
    video.write_bytes(b"v")

    def _fake_post(url, **kwargs):
        if url.endswith("/finalize"):
            return _FakeResponse(200, {"data": {"id": "1", "processing_info": {"state": "failed"}}})
        return _FakeResponse(200, {"data": {"id": "1"}})

    monkeypatch.setattr(post_to_x.requests, "post", _fake_post)
    with pytest.raises(SystemExit):
        post_to_x.upload_video(video, _CREDS)


def test_weighted_length_counts_any_url_as_23(post_to_x):
    long_url = "https://www.nullstock.im/?prompt=" + "%EA%B0%80" * 200
    assert post_to_x.weighted_length(f"가 {long_url}") == 2 + 1 + 23


def test_strategy_open_url_prefills_home_with_utm(post_to_x):
    from urllib.parse import parse_qs, urlsplit

    prompt = "KOSPI 종목 중 RSI가 30 아래로 내려가면 매수하고, 손절은 -8%로 해 주세요."
    url = post_to_x.strategy_open_url(f"  {prompt}\n", "myth-01")
    parts = urlsplit(url)
    # 비로그인 방문자를 홈으로 돌려보내며 쿼리를 잃는 경로가 아니라 홈 자체로 보낸다(2026-10-10 실측)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == "https://www.nullstock.im/"
    assert parse_qs(parts.query) == {
        "prompt": [prompt], "utm_source": ["x"], "utm_medium": ["social"], "utm_campaign": ["myth-01"],
    }
    assert " " not in url  # 공백이 남으면 X가 링크를 거기서 끊는다


def test_strategy_open_url_rejects_empty_or_too_long(post_to_x):
    with pytest.raises(SystemExit):
        post_to_x.strategy_open_url("  ", "myth-01")
    with pytest.raises(SystemExit):
        post_to_x.strategy_open_url("가" * (post_to_x.MAX_OPEN_LINK_PROMPT_LENGTH + 1), "myth-01")
    with pytest.raises(SystemExit):
        post_to_x.strategy_open_url("문장", " ")


def test_open_link_is_appended_to_preview(post_to_x, monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(post_to_x.requests, "post", lambda *a, **k: (_ for _ in ()).throw(AssertionError("전송됨")))
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("RSI 30 아래면 매수", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["post_to_x.py", "본문", "--open-link", str(prompt_file), "--campaign", "myth-01"])
    post_to_x.main()
    out = capsys.readouterr().out
    assert "이 전략 그대로 열기: https://www.nullstock.im/?prompt=" in out
    monkeypatch.setattr(sys, "argv", ["post_to_x.py", "본문", "--open-link", str(prompt_file)])
    with pytest.raises(SystemExit):  # --campaign 없이 링크만은 받지 않는다
        post_to_x.main()
