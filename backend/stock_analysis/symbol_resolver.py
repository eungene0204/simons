"""
종목명 ↔ 종목코드 해석기.

`data/korea-stocks.json`(symbol/name/market/sector/industry)을 1회 로드해
사용자 입력 문자열에서 종목을 식별한다. 대표 해외 종목은 작은 별칭 맵으로만
인식하되 코드는 티커로 둔다(국내 parquet 데이터가 없어 분석 단계에서
INSUFFICIENT_DATA로 처리된다).

새 의존성 없이 표준 라이브러리만 사용한다(KISS).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_STOCKS_JSON_PATH = Path(__file__).resolve().parents[2] / "data" / "korea-stocks.json"

# 분석 데이터(parquet)는 없지만 intent 분류에서 '종목 질문'으로 인식해야 하는 대표 해외 종목.
_OVERSEAS_ALIASES: dict[str, str] = {
    "엔비디아": "NVDA",
    "nvidia": "NVDA",
    "애플": "AAPL",
    "apple": "AAPL",
    "테슬라": "TSLA",
    "tesla": "TSLA",
    "마이크로소프트": "MSFT",
    "구글": "GOOGL",
    "아마존": "AMZN",
    "메타": "META",
}

# 국내 종목의 '등록명이 아닌 흔한 통칭'. korea-stocks.json의 등록명만으로는 못 잡는
# 일상 표현을 보강한다(예: '현대차'=현대자동차, '네이버'=NAVER, '하이닉스'=SK하이닉스).
# 충돌 안전성은 별칭도 등록명과 함께 '가장 긴 이름 우선' 인덱스(_match_index)에 넣어
# 보장한다(예: '하이닉스'(4) > '이닉스'(3)이므로 '이닉스'를 잘못 집지 않는다).
# 보수적으로, 모호하지 않은 통칭만 등록한다. '삼성'·'현대'·'LG'처럼 그 자체로 여러
# 계열사를 가리키는 접두어는 일부러 넣지 않는다(애매 입력은 무매칭이 안전).
_KOREAN_ALIASES: dict[str, str] = {
    "현대차": "005380",          # 현대자동차
    "네이버": "035420",          # NAVER
    "하이닉스": "000660",        # SK하이닉스
    "에스케이하이닉스": "000660",
    "sk hynix": "000660",
}


@dataclass(frozen=True)
class StockRef:
    symbol: str
    name: str
    market: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    overseas: bool = False


@lru_cache(maxsize=1)
def _load_stocks() -> list[dict]:
    try:
        with _STOCKS_JSON_PATH.open(encoding="utf-8") as fh:
            data = json.load(fh)
        return [row for row in data if isinstance(row, dict) and row.get("symbol") and row.get("name")]
    except Exception:
        logger.exception("korea-stocks.json 로드 실패: %s", _STOCKS_JSON_PATH)
        return []


@lru_cache(maxsize=1)
def _match_index() -> tuple[tuple[str, dict], ...]:
    """매칭 문자열 길이 내림차순으로 정렬된 (match_str, row) 목록.

    등록명과 국내 통칭(_KOREAN_ALIASES)을 한 인덱스에 합쳐 '가장 긴 이름 우선'으로
    매칭한다. 별칭도 같은 길이 정렬을 거치므로 '하이닉스'가 '이닉스'보다 먼저 잡혀
    충돌이 발생하지 않는다(별칭은 해당 등록 row로 해석된다)."""
    rows = _load_stocks()
    by_symbol = {str(row["symbol"]).strip(): row for row in rows}
    indexed: list[tuple[str, dict]] = [
        (str(row["name"]).strip(), row) for row in rows if len(str(row["name"]).strip()) >= 2
    ]
    for alias, ticker in _KOREAN_ALIASES.items():
        row = by_symbol.get(ticker)
        if row is not None and len(alias) >= 2:
            indexed.append((alias, row))
    indexed.sort(key=lambda item: len(item[0]), reverse=True)
    return tuple(indexed)


@lru_cache(maxsize=1)
def _symbol_index() -> dict[str, dict]:
    return {str(row["symbol"]).strip(): row for row in _load_stocks()}


def resolve_by_symbol(symbol: str) -> Optional[StockRef]:
    if not symbol:
        return None
    row = _symbol_index().get(symbol.strip())
    if row is None:
        # 해외 티커(별칭 맵의 값)도 허용한다.
        if symbol.strip().upper() in set(_OVERSEAS_ALIASES.values()):
            return StockRef(symbol=symbol.strip().upper(), name=symbol.strip().upper(), overseas=True)
        return None
    return StockRef(
        symbol=str(row["symbol"]).strip(),
        name=str(row["name"]).strip(),
        market=row.get("market"),
        sector=row.get("sector"),
        industry=row.get("industry"),
    )


# ── 한글 자모(초/중/종성) 분해 기반 오타 근접 매칭 ──────────────────────────────────
# 종목명 오타('삼서전자'→'삼성전자')를 잡는다. 문자 단위 편집거리는 '삼서전자'를 삼성전자와
# 삼지전자 둘 다 1글자 차이로 봐 엉뚱한 종목(삼지전자)을 고를 수 있다. 자모 단위로 풀면
# 서(ㅅㅓ)↔성(ㅅㅓㅇ)=종성 ㅇ 하나 차이(거리 1)라 삼성전자(1)가 삼지전자(2)를 명확히
# 앞선다 — 한글 오타 교정엔 자모 거리가 정답을 안정적으로 고른다. LLM(티커 환각)보다 정밀.
_HANGUL_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_HANGUL_JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_HANGUL_JONG = ["", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ", "ㄻ", "ㄼ",
                "ㄽ", "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅊ",
                "ㅋ", "ㅌ", "ㅍ", "ㅎ"]


def _to_jamo(text: str) -> str:
    """한글 음절을 초/중/종성 자모열로 분해한다(비한글은 그대로, 소문자화)."""
    out: list[str] = []
    for ch in text.lower():
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3:
            idx = code - 0xAC00
            out.append(_HANGUL_CHO[idx // 588])
            out.append(_HANGUL_JUNG[(idx % 588) // 28])
            jong = _HANGUL_JONG[idx % 28]
            if jong:
                out.append(jong)
        elif not ch.isspace():
            out.append(ch)
    return "".join(out)


def _edit_distance(a: str, b: str, cap: int) -> int:
    """레벤슈타인 거리. cap 초과가 확실하면 조기 중단(cap+1 반환)."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        row_min = cur[0]
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            row_min = min(row_min, cur[j])
        if row_min > cap:
            return cap + 1
        prev = cur
    return prev[-1]


@lru_cache(maxsize=1)
def _jamo_index() -> tuple[tuple[str, dict], ...]:
    """(종목명/통칭의 자모열, row) 목록 — 오타 근접 매칭용(_match_index와 동일 원천)."""
    return tuple((_to_jamo(match_str), row) for match_str, row in _match_index())


def suggest_similar_stocks(query: str, *, max_distance: int = 2) -> list[StockRef]:
    """오타로 추정되는 종목명 후보를 자모 편집거리로 찾는다(정확 매칭 실패 시 폴백용).

    보수적으로 '자신 있는' 후보만 반환한다 — 조용한 오교정 대신 사용자 확인을 위한 것이라
    거짓 후보는 비용이 크다. 조건: 자모거리 ≤ max_distance, 거리 ≤ 40%×질의 자모길이,
    최선 후보가 차선보다 엄격히 가까움(margin ≥ 1 — '삼서전자'가 삼성전자·삼지전자에 동률이면
    아무것도 제안하지 않는다). 질의는 2글자 이상 한글이어야 한다(짧은 토큰 오매칭 방지).
    """
    q = (query or "").strip()
    if len(q) < 2 or not all("가" <= ch <= "힣" for ch in q):
        return []
    if resolve_by_symbol(q) is not None:  # 코드면 오타 아님
        return []
    qj = _to_jamo(q)
    if not qj:
        return []
    ratio_cap = int(len(qj) * 0.4)
    cap = min(max_distance, ratio_cap)
    if cap < 1:
        return []
    scored: list[tuple[int, dict]] = []
    seen: set[str] = set()
    for target_jamo, row in _jamo_index():
        d = _edit_distance(qj, target_jamo, cap)
        if d <= cap and str(row["name"]) != q:
            sym = str(row["symbol"]).strip()
            if sym not in seen:
                seen.add(sym)
                scored.append((d, row))
    if not scored:
        return []
    scored.sort(key=lambda item: (item[0], str(item[1]["name"])))
    best_d = scored[0][0]
    runner_up = next((d for d, _ in scored if d > best_d), None)
    if runner_up is not None and runner_up - best_d < 1:  # 동률 최선 → 애매 → 제안 안 함
        return []
    return [
        StockRef(
            symbol=str(row["symbol"]).strip(), name=str(row["name"]).strip(),
            market=row.get("market"), sector=row.get("sector"), industry=row.get("industry"),
        )
        for d, row in scored if d == best_d
    ]


def _is_valid_boundary(text: str, pos: int, is_after: bool) -> bool:
    """주어진 위치가 종목명의 경계인지 검사한다.
    - is_after=False: pos 이전 문자가 경계 조건 만족?
    - is_after=True: pos 이후 문자가 경계 조건 만족?
    경계 조건: 문자가 없거나, 한글 글자가 아니거나, 조사/기호
    """
    if is_after:
        if pos >= len(text):
            return True
        ch = text[pos]
        # 영숫자가 이어지면 영문 단어의 일부다 — 'strategy' 안의 'EG', 'backtest DB' 같은
        # 짧은 영문 종목명(EG·DB·NC 등)의 오매칭 방지(레드팀 QA 17-3).
        if ch.isascii() and ch.isalnum():
            return False
        # 한글 글자가 아니면 경계 (띄어쓰기, 기호 등)
        if not ('가' <= ch <= '힯'):  # 가-힣 범위만 체크
            return True
        # 한글 글자이더라도 조사(와, 은, 는, 이, 가, 을, 를, 도 등)면 경계로 본다.
        # '에/로/으(로)/의/만/과/랑'도 포함 — "삼성전자에 골든크로스 적용", "하이닉스로 바꿔줘",
        # "삼성전자만" 같은 지정 종목 발화(FR-STR-068)가 경계 불인정으로 무매칭되던 것 보정.
        if ch in '와과을를이가도은는에로으의만랑':
            return True
        return False
    else:
        if pos < 0:
            return True
        ch = text[pos]
        if ch.isascii() and ch.isalnum():
            return False
        if not ('가' <= ch <= '힯'):
            return True
        return False


def find_in_text(text: str) -> list[StockRef]:
    """입력 문자열에서 등장하는 종목을 식별한다(가장 긴 이름 우선, 중복 제거)."""
    if not text:
        return []
    found: list[StockRef] = []
    seen: set[str] = set()
    remaining = text

    # 1) 국내 종목명·통칭(가장 긴 이름부터) — 단어 경계를 고려해 정확히 매칭 (대소문자 무시)
    remaining_lower = text.lower()
    for match_str, row in _match_index():
        # 대소문자 무시 substring 검색
        match_lower = match_str.lower()
        idx = 0
        while True:
            idx = remaining_lower.find(match_lower, idx)
            if idx == -1:
                break
            # 앞 경계 검사 (원본 텍스트 기준)
            before_valid = _is_valid_boundary(text, idx - 1, is_after=False)
            # 뒤 경계 검사 (원본 텍스트 기준)
            after_valid = _is_valid_boundary(text, idx + len(match_str), is_after=True)

            if before_valid and after_valid and row["symbol"] not in seen:
                # 별칭으로 매칭됐더라도 항상 등록명(canonical)을 반환한다.
                found.append(
                    StockRef(
                        symbol=str(row["symbol"]).strip(),
                        name=str(row["name"]).strip(),
                        market=row.get("market"),
                        sector=row.get("sector"),
                        industry=row.get("industry"),
                    )
                )
                seen.add(row["symbol"])
                # 매칭된 부분만 공백으로 치환 (remaining_lower와 text 동시 갱신)
                remaining_lower = remaining_lower[:idx] + " " * len(match_str) + remaining_lower[idx + len(match_str):]
                text = text[:idx] + " " * len(match_str) + text[idx + len(match_str):]
                break  # 같은 종목은 한 번만 추가
            idx += 1

    # 2) 6자리 종목코드 직접 입력 — 숫자 6자리 + 일부 종목(스팩/신규상장 등)의
    #    영문 포함 코드(예: '0126Z0')도 인식한다. 첫 글자가 숫자라 영단어 오탐을 피한다.
    #    \b는 유니코드 단어 경계라 한글 조사가 붙은 "005930에"를 놓친다 → 영숫자 부재
    #    lookaround로 경계를 판정한다.
    for code in re.findall(r"(?<![0-9A-Za-z])\d[0-9A-Za-z]{5}(?![0-9A-Za-z])", remaining):
        code = code.upper()
        if code not in seen and code in _symbol_index():
            ref = resolve_by_symbol(code)
            if ref:
                found.append(ref)
                seen.add(code)

    # 3) 대표 해외 종목 별칭
    lowered = text.lower()
    for alias, ticker in _OVERSEAS_ALIASES.items():
        if alias in lowered and ticker not in seen:
            found.append(StockRef(symbol=ticker, name=alias, overseas=True))
            seen.add(ticker)

    return found
