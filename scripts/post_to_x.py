"""X(트위터) 계정에 글을 올린다 — POST /2/tweets, OAuth 1.0a(사용자 컨텍스트).

기본은 **미리보기(dry-run)** 다 — 올릴 글과 가중 글자 수만 보여 주고 아무것도 보내지 않는다.
실제로 올리려면 `--post`를 명시한다(되돌리기 어려운 외부 전송이라 기본값으로 두지 않는다).

필요한 환경 변수(.env — `--post`일 때만 읽는다. 값을 코드·대화에 적지 않는다):
  X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET
  ※ Access Token은 앱 권한을 Read and Write로 바꾼 **뒤** 발급해야 게시가 된다.

사용법:
  uv run python scripts/post_to_x.py "올릴 글"              # 미리보기
  uv run python scripts/post_to_x.py --file draft.txt       # 파일 내용으로 미리보기
  uv run python scripts/post_to_x.py "올릴 글" --post       # 실제 게시

선택 옵션(미리보기·게시 공통):
  --quote <트윗 URL 또는 id>   그 글을 인용해서 올린다
  --reply-to <트윗 URL 또는 id> 그 글의 답글로 올린다(스레드 잇기)
  --image <파일> (최대 4장)    사진을 첨부한다 — PNG/JPEG, 파일당 5MB 이하
  --video <파일>               동영상 1개를 첨부한다 — MP4(H.264), 512MB 이하, 사진과 같이 못 붙인다
  --long                       280을 넘는 긴 글 허용(Premium 계정만 X가 받아 준다)
  --open-link <파일>           그 파일의 전략 문장으로 "이 전략 그대로 열기" 링크를 글 끝에 붙인다
                               (널스탁 홈 `/?prompt=…` — 입력창에 채우기만 하고 보내기는 방문자가 누른다)
  --campaign <이름>            링크의 utm_campaign(예: myth-01). --open-link와 함께 쓴다
성공하면 마지막 줄이 `POSTED_ID=<id>` 라서 다음 답글의 --reply-to에 이어 쓸 수 있다.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import os
import re
import secrets
import sys
import time
from pathlib import Path
from urllib.parse import quote, urlencode

import requests

ROOT = Path(__file__).resolve().parents[1]

TWEETS_URL = "https://api.x.com/2/tweets"
MEDIA_UPLOAD_URL = "https://api.x.com/2/media/upload"
MAX_WEIGHTED_LENGTH = 280
MAX_LONG_WEIGHTED_LENGTH = 25000  # 긴 글(Premium) 한도 — --long일 때만 적용
MAX_IMAGES = 4
MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
MAX_VIDEO_BYTES = 512 * 1024 * 1024
VIDEO_CHUNK_BYTES = 4 * 1024 * 1024  # append 한 조각 한도는 5MB
VIDEO_PROCESSING_TIMEOUT = 300
REQUEST_TIMEOUT = 15
SITE_URL = "https://www.nullstock.im"
# 링크를 받는 쪽 한도(lib/strategy/strategyOpenLink.ts MAX_STRATEGY_PROMPT_LENGTH)와 같아야 한다
MAX_OPEN_LINK_PROMPT_LENGTH = 1000
OPEN_LINK_LABEL = "이 전략 그대로 열기"
CREDENTIAL_ENV = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")

# X가 글자 수를 셀 때 가중치 1로 치는 범위(나머지 — 한글·한자·이모지 등 — 는 2).
_WEIGHT_1_RANGES = ((0x0000, 0x10FF), (0x2000, 0x200D), (0x2010, 0x201F), (0x2032, 0x2037))


# X는 링크를 t.co로 줄여 길이와 무관하게 23으로 센다
_URL_RE = re.compile(r"https?://\S+")
URL_WEIGHT = 23


def weighted_length(text: str) -> int:
    """X 기준 가중 글자 수. 한글 한 글자는 2, 영문·숫자·공백은 1, 링크 하나는 23이다."""
    urls = _URL_RE.findall(text)
    rest = _URL_RE.sub("", text)
    return URL_WEIGHT * len(urls) + sum(
        1 if any(lo <= ord(ch) <= hi for lo, hi in _WEIGHT_1_RANGES) else 2
        for ch in rest
    )


def _pct(value: str) -> str:
    """RFC 3986 퍼센트 인코딩(OAuth 1.0a 규격)."""
    return quote(str(value), safe="~")


def oauth_header(
    method: str,
    url: str,
    *,
    api_key: str,
    api_secret: str,
    access_token: str,
    access_token_secret: str,
    extra_params: dict[str, str] | None = None,
    nonce: str | None = None,
    timestamp: str | None = None,
) -> str:
    """OAuth 1.0a HMAC-SHA1 Authorization 헤더 값을 만든다.

    JSON 본문은 서명 대상이 아니다 — 폼 본문·쿼리 파라미터가 있을 때만 `extra_params`로 넘긴다.
    """
    oauth_params = {
        "oauth_consumer_key": api_key,
        "oauth_nonce": nonce or secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": timestamp or str(int(time.time())),
        "oauth_token": access_token,
        "oauth_version": "1.0",
    }
    signed = {**oauth_params, **(extra_params or {})}
    param_string = "&".join(f"{_pct(k)}={_pct(v)}" for k, v in sorted(signed.items()))
    base_string = "&".join((method.upper(), _pct(url), _pct(param_string)))
    signing_key = f"{_pct(api_secret)}&{_pct(access_token_secret)}"
    digest = hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
    oauth_params["oauth_signature"] = base64.b64encode(digest).decode()
    return "OAuth " + ", ".join(f'{_pct(k)}="{_pct(v)}"' for k, v in sorted(oauth_params.items()))


def load_credentials() -> dict[str, str]:
    """`.env`에서 게시용 자격 증명을 읽는다. 하나라도 비면 이름만 알리고 중단한다(Fail Fast)."""
    from dotenv import load_dotenv  # 모듈 레벨 금지 — .env 오염 함정

    load_dotenv(ROOT / ".env")
    missing = [name for name in CREDENTIAL_ENV if not os.environ.get(name)]
    if missing:
        sys.exit(f"[중단] .env에 없는 변수: {', '.join(missing)}")
    return {
        "api_key": os.environ["X_API_KEY"],
        "api_secret": os.environ["X_API_SECRET"],
        "access_token": os.environ["X_ACCESS_TOKEN"],
        "access_token_secret": os.environ["X_ACCESS_TOKEN_SECRET"],
    }


def tweet_id_from(ref: str) -> str:
    """트윗 URL(`.../status/<id>?s=20`) 또는 id 문자열에서 숫자 id만 뽑는다."""
    tweet_id = ref.strip().split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    if not tweet_id.isdigit():
        sys.exit(f"[중단] 트윗 id를 알 수 없다: {ref}")
    return tweet_id


def strategy_open_url(prompt: str, campaign: str) -> str:
    """전략 문장을 입력창에 채워 여는 널스탁 링크. 로그인 전 방문자도 열리는 홈(`/`)으로 보낸다
    — 다른 경로는 비로그인 방문자를 홈으로 돌려보내면서 쿼리를 잃는다(2026-10-10 실측)."""
    prompt = prompt.strip()
    if not prompt:
        sys.exit("[중단] 링크에 넣을 전략 문장이 비었다")
    if len(prompt) > MAX_OPEN_LINK_PROMPT_LENGTH:
        sys.exit(f"[중단] 전략 문장이 {MAX_OPEN_LINK_PROMPT_LENGTH}자를 넘으면 앱이 채우지 않는다")
    if not campaign.strip():
        sys.exit("[중단] --campaign이 비었다")
    query = urlencode(
        {"prompt": prompt, "utm_source": "x", "utm_medium": "social", "utm_campaign": campaign.strip()},
        quote_via=quote,
    )
    return f"{SITE_URL}/?{query}"


def check_images(paths: list[Path]) -> None:
    """첨부 사진의 개수·존재·형식·크기를 보내기 전에 검사한다(Fail Fast)."""
    if len(paths) > MAX_IMAGES:
        sys.exit(f"[중단] 사진은 최대 {MAX_IMAGES}장")
    for path in paths:
        if not path.is_file():
            sys.exit(f"[중단] 사진 파일이 없다: {path}")
        if path.suffix.lower() not in IMAGE_MEDIA_TYPES:
            sys.exit(f"[중단] PNG/JPEG만 올릴 수 있다: {path}")
        if path.stat().st_size > MAX_IMAGE_BYTES:
            sys.exit(f"[중단] 5MB를 넘는다: {path}")


def upload_image(path: Path, credentials: dict[str, str]) -> str:
    """사진을 올리고 media id를 돌려준다. multipart 본문은 서명 대상이 아니다."""
    with path.open("rb") as fh:
        response = requests.post(
            MEDIA_UPLOAD_URL,
            headers={"Authorization": oauth_header("POST", MEDIA_UPLOAD_URL, **credentials)},
            files={"media": (path.name, fh, IMAGE_MEDIA_TYPES[path.suffix.lower()])},
            data={"media_category": "tweet_image"},
            timeout=REQUEST_TIMEOUT * 4,
        )
    if response.status_code != 200:
        sys.exit(f"[사진 업로드 실패] {path.name} HTTP {response.status_code}: {response.text}")
    return response.json()["data"]["id"]


def check_video(path: Path, images: list[Path]) -> None:
    """첨부 동영상의 존재·형식·크기를 보내기 전에 검사한다. X는 동영상과 사진을 한 글에 같이 받지 않는다."""
    if images:
        sys.exit("[중단] 동영상과 사진은 한 글에 같이 붙일 수 없다")
    if not path.is_file():
        sys.exit(f"[중단] 동영상 파일이 없다: {path}")
    if path.suffix.lower() != ".mp4":
        sys.exit(f"[중단] MP4만 올릴 수 있다: {path}")
    if path.stat().st_size > MAX_VIDEO_BYTES:
        sys.exit(f"[중단] 512MB를 넘는다: {path}")


def upload_video(path: Path, credentials: dict[str, str]) -> str:
    """동영상을 조각 업로드(initialize → append → finalize)하고, X가 처리를 마칠 때까지 기다려 media id를 돌려준다."""
    auth = lambda method, url, params=None: {  # noqa: E731 — 요청마다 새 nonce로 서명한다
        "Authorization": oauth_header(method, url, **credentials, extra_params=params)
    }
    init_url = f"{MEDIA_UPLOAD_URL}/initialize"
    response = requests.post(
        init_url,
        json={"media_type": "video/mp4", "total_bytes": path.stat().st_size, "media_category": "tweet_video"},
        headers=auth("POST", init_url),
        timeout=REQUEST_TIMEOUT,
    )
    if response.status_code != 200:
        sys.exit(f"[동영상 업로드 실패] initialize HTTP {response.status_code}: {response.text}")
    media_id = response.json()["data"]["id"]

    append_url = f"{MEDIA_UPLOAD_URL}/{media_id}/append"
    with path.open("rb") as fh:
        for index, chunk in enumerate(iter(lambda: fh.read(VIDEO_CHUNK_BYTES), b"")):
            response = requests.post(
                append_url,
                headers=auth("POST", append_url),
                files={"media": (path.name, chunk, "application/octet-stream")},
                data={"segment_index": str(index)},
                timeout=REQUEST_TIMEOUT * 4,
            )
            if response.status_code not in (200, 204):
                sys.exit(f"[동영상 업로드 실패] append {index} HTTP {response.status_code}: {response.text}")

    finalize_url = f"{MEDIA_UPLOAD_URL}/{media_id}/finalize"
    response = requests.post(finalize_url, headers=auth("POST", finalize_url), timeout=REQUEST_TIMEOUT)
    if response.status_code != 200:
        sys.exit(f"[동영상 업로드 실패] finalize HTTP {response.status_code}: {response.text}")
    info = response.json()["data"].get("processing_info")

    # X가 인코딩을 마치기 전에 글을 올리면 거부된다 — succeeded가 될 때까지 상태를 묻는다
    deadline = time.monotonic() + VIDEO_PROCESSING_TIMEOUT
    while info and info.get("state") in ("pending", "in_progress"):
        if time.monotonic() > deadline:
            sys.exit(f"[동영상 업로드 실패] 처리 대기 {VIDEO_PROCESSING_TIMEOUT}초 초과: {media_id}")
        time.sleep(info.get("check_after_secs", 2))
        params = {"command": "STATUS", "media_id": media_id}
        response = requests.get(
            MEDIA_UPLOAD_URL, params=params, headers=auth("GET", MEDIA_UPLOAD_URL, params), timeout=REQUEST_TIMEOUT
        )
        if response.status_code != 200:
            sys.exit(f"[동영상 업로드 실패] status HTTP {response.status_code}: {response.text}")
        info = response.json()["data"].get("processing_info")
    if info and info.get("state") != "succeeded":
        sys.exit(f"[동영상 업로드 실패] 처리 상태 {info}")
    return media_id


def post_tweet(
    text: str,
    credentials: dict[str, str],
    *,
    quote_id: str | None = None,
    reply_to_id: str | None = None,
    media_ids: list[str] | None = None,
) -> str:
    """글을 올리고 게시물 id를 돌려준다. 실패하면 상태 코드와 응답 본문을 담아 중단한다."""
    body: dict = {"text": text}
    if quote_id:
        body["quote_tweet_id"] = quote_id
    if reply_to_id:
        body["reply"] = {"in_reply_to_tweet_id": reply_to_id}
    if media_ids:
        body["media"] = {"media_ids": media_ids}
    response = requests.post(
        TWEETS_URL,
        json=body,
        headers={"Authorization": oauth_header("POST", TWEETS_URL, **credentials)},
        timeout=REQUEST_TIMEOUT,
    )
    if response.status_code != 201:
        sys.exit(f"[게시 실패] HTTP {response.status_code}: {response.text}")
    return response.json()["data"]["id"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("text", nargs="?", help="올릴 글")
    ap.add_argument("--file", type=Path, help="글을 파일에서 읽는다(text와 동시 사용 불가)")
    ap.add_argument("--post", action="store_true", help="실제로 게시한다(없으면 미리보기만)")
    ap.add_argument("--quote", help="인용할 트윗 URL 또는 id")
    ap.add_argument("--reply-to", help="답글로 이을 트윗 URL 또는 id")
    ap.add_argument("--image", type=Path, action="append", default=[], help="첨부할 사진(최대 4장)")
    ap.add_argument("--video", type=Path, help="첨부할 동영상(MP4 1개, 사진과 같이 못 붙인다)")
    ap.add_argument("--open-link", type=Path, help="이 파일의 전략 문장으로 '이 전략 그대로 열기' 링크를 붙인다")
    ap.add_argument("--campaign", help="링크의 utm_campaign(--open-link와 함께)")
    ap.add_argument("--long", action="store_true", help="긴 글 허용(280 → 25,000). Premium 계정만 X가 받아 준다")
    args = ap.parse_args()

    if bool(args.text) == bool(args.file):
        ap.error("글은 text 인자와 --file 중 하나만 준다")
    text = (args.file.read_text(encoding="utf-8") if args.file else args.text).strip()
    if not text:
        sys.exit("[중단] 빈 글은 올릴 수 없다")
    if (args.open_link is None) != (args.campaign is None):
        ap.error("--open-link와 --campaign은 함께 준다")
    if args.open_link is not None:
        url = strategy_open_url(args.open_link.read_text(encoding="utf-8"), args.campaign)
        text = f"{text}\n\n{OPEN_LINK_LABEL}: {url}"

    limit = MAX_LONG_WEIGHTED_LENGTH if args.long else MAX_WEIGHTED_LENGTH
    length = weighted_length(text)
    print(f"--- 올릴 글 (가중 {length}/{limit}) ---\n{text}\n---")
    if length > limit:
        sys.exit(f"[중단] {length - limit}자 초과 — 한글은 한 글자가 2로 센다")

    # 빈 문자열("")도 값으로 취급해 검증한다 — 앞 단계 실패로 id가 빈 채 넘어오면 조용히 단독 글이 된다
    quote_id = tweet_id_from(args.quote) if args.quote is not None else None
    reply_to_id = tweet_id_from(args.reply_to) if args.reply_to is not None else None
    check_images(args.image)
    if args.video is not None:
        check_video(args.video, args.image)
    if quote_id:
        print(f"인용: {quote_id}")
    if reply_to_id:
        print(f"답글 대상: {reply_to_id}")
    if args.image:
        print("사진: " + ", ".join(path.name for path in args.image))
    if args.video:
        print(f"동영상: {args.video.name} ({args.video.stat().st_size / 1024 / 1024:.1f}MB)")

    if not args.post:
        print("미리보기만 했습니다. 실제로 올리려면 --post 를 붙이세요.")
        return

    credentials = load_credentials()
    media_ids = [upload_image(path, credentials) for path in args.image]
    if args.video:
        media_ids.append(upload_video(args.video, credentials))
    tweet_id = post_tweet(
        text, credentials, quote_id=quote_id, reply_to_id=reply_to_id, media_ids=media_ids
    )
    print(f"게시 완료: https://x.com/i/web/status/{tweet_id}")
    print(f"POSTED_ID={tweet_id}")


if __name__ == "__main__":
    main()
