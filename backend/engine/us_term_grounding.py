"""미국 용어 그라운딩 — 카탈로그 밖 테마어를 SEC 공시 전문검색으로 학습해 구성 티커로 매핑.

한국 그라운딩(engine/term_grounding.py)과 **같은 계약, 다른 소스**다:

- **입력은 LLM이 뽑은 짧은 테마어다**(사용자 원문이 아님 — 자연어 해석 구조 원칙 § 3-2).
  원문 스캔·키워드 매칭은 없다.
- **1차 소스는 SEC EDGAR 전문검색**(efts.sec.gov, 키 불필요). 결과가 CIK로 오므로
  정본(us-stocks.json의 cik 5,939곳)에 **결정론 조인**된다 — 한국처럼 뉴스 본문에서
  종목명을 긁을 필요가 없다. 근거는 기자의 해석이 아니라 **기업 자신의 공시 기술**이라
  구성 목록이 객관적 소속 정보(사실)라는 규제 계약과도 맞는다.
- **언급 ≠ 소속**: 공시 히트는 후보일 뿐이다(실측: "quantum computing" 질의에 보험
  중개사·소매업체가 리스크 요인 문장으로 걸린다). 소속 판정은 LLM이 **닫힌 후보 목록**
  위에서만 한다(목록 밖 티커는 드롭 — 환각 차단).
- **학습 저장·재검색 금지**: 결과는 data/us-term-lexicon.json에 영속되고, US 지식그래프가
  이를 학습 오버레이로 합성해(us_knowledge_graph) 다음부터는 검색 없이 결정론으로 풀린다.
  검색 자체가 실패(네트워크·차단)하면 저장하지 않는다 — 복구 후 재시도 가능.
- **검토 상태**: 서로 다른 공시 2건 이상이 지지하면 자동 verified, 1건이면 pending
  (관리자 콘솔 승인 대기 — 그래프에 합성되지 않는다). 한국 계약과 동일.

[시장 격리] 이 모듈은 한국 기계(engine/term_grounding·knowledge_graph·nl_parser·
naver_*)를 **import하지 않는다**. 미국 전략에 한국 종목이 실리던 2026-08-26 사고의
재발 경로를 차단하는 것이 US 레인을 따로 두는 이유다(test_us_region_isolation이 강제).
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from engine.console_logging import console_logger

logger = console_logger("us_term_grounding", "US-GROUND")

_BASE_DIR = Path(__file__).resolve().parent.parent.parent  # 레포 루트(data/의 부모)
_LEXICON_PATH = _BASE_DIR / "data" / "us-term-lexicon.json"
_STOCKS_PATH = _BASE_DIR / "data" / "us-stocks.json"
_OHLCV_DIR = _BASE_DIR / "data" / "ohlcv-us"
_LEXICON_LOCK = threading.Lock()

# SEC 전문검색 게이트웨이 — API 키가 없는 대신 연락처가 담긴 User-Agent가 필수다
# (없으면 403). 초당 10요청 제한이라 페이지 사이에 간격을 둔다.
_EDGAR_ENDPOINT = "https://efts.sec.gov/LATEST/search-index"
_EDGAR_ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{adsh}/{doc}"
_SEARCH_TIMEOUT_S = 8
_PAGE_SIZE = 100          # EDGAR 고정 페이지 크기
_MAX_PAGES = 3            # 상위 300건 — 지지 건수 상위 후보를 뽑기에 충분(실측)
_PAGE_INTERVAL_S = 0.2
_FORMS = "10-K,20-F"      # 연차보고서 — 사업 기술이 실리는 문서(보도자료 첨부 제외)
_LOOKBACK_DAYS = 365 * 3  # 최근 3년 공시 — 지속적 사업 기술인지 볼 수 있는 창

# 후보 상한 — LLM 심사 프롬프트에 싣는 최대 종목 수(관련도 상위)
_CANDIDATE_MAX = 40
# 선별력 게이트 — '언급'이 소속의 증거가 되지 못하는 상투어를 걸러낸다. 두 신호를 **함께**
# 본다: ① 공시 등장 건수가 흔한 축이고 ② 상위 후보의 업종이 흩어져 있으면 상투어다.
#
# 한쪽만 보면 멀쩡한 테마가 막힌다 — 실측(2026-08-27, 상위 20곳의 GICS 섹터 집중도):
#   흔함만으로 판정 → 'cancer' 4,261건·'oncology' 2,946건이 막힌다(집중도 95%,
#     후보가 전부 항암 기업이라 관련도 순위가 이미 정리해 준 경우다 — 사용자 실측 사고)
#   흩어짐만으로 판정 → 'data center power' 35%(정보기술 7·산업재 6)가 막힌다
#     (83건짜리 희소 표현이라 흩어짐이 곧 상투어를 뜻하지 않는다)
#   둘 다 걸리는 것만 상투어 → climate change 10,000건·40%, supply chain 10,000·35%,
#     inflation 10,000·40%, cybersecurity 10,000·30%, artificial intelligence 10,000·35%
#     ('climate change'를 학습시키면 셸·EOG·BHP·금광이 확정 15곳으로 나온다 — 기후
#      테마 기업이 아니라 기후 위험을 공시해야 하는 배출 기업이다)
# 통과하는 테마 실측: cancer 95%·oncology 95%·mrna 90%·airline 90%·quantum 75%·
#   humanoid robot 75%·cloud software 60%(임계 50%와 여유 있게 갈린다)
_COMMON_TOTAL_HITS = 2000      # ① 흔함 기준(전체 히트)
_TOP_CONCENTRATION_N = 20      # ② 집중도를 재는 상위 후보 수
_MIN_SECTOR_SHARE = 0.5        # ② 최다 섹터가 이 비율 미만이면 '흩어짐'
# LLM 소속 심사 한 번에 싣는 후보 수 — 위 _judge_members 주석의 실측 근거 참조
_JUDGE_BATCH = 10
# 자동 verified 승격 기준 — 서로 다른 공시 몇 건이 같은 기업을 지지하는지
_AUTO_VERIFY_SUPPORT = 2
# 테마 유니버스 최소 구성 — 미만이면 테마로 세우지 않는다(2종목짜리 '테마'는 잡음).
# 카탈로그 빌더(scripts/build_us_theme_catalog.py)의 MIN_MEMBERS와 같은 눈높이.
_MIN_MEMBERS = 4
# 학습 항목 재검토 TTL(일) — 경과 항목은 재언급 시 조건부 재학습(부정 캐시 영구 고착 방지)
_REGROUND_TTL_DAYS_DEFAULT = 90.0

# chat 계약은 공유 파서와 동일: (system_prompt, user_msg, *, max_tokens) -> str
ChatFn = Callable[..., str]
# search_fn(term) -> {"total": 전체 히트 수, "filings": [...]} | None(검색 실패 —
# 빈 결과와 구분해 저장하지 않는다). total은 선별력 게이트(_MAX_TOTAL_HITS)가 읽는다.
SearchFn = Callable[[str], Optional[dict]]


def grounding_available() -> bool:
    """검색 그라운딩을 시도할 수 있는가 — 키는 없고 차단 스위치만 본다.

    US_TERM_GROUNDING=off면 카탈로그만 쓰던 종전 동작으로 되돌아간다(운영 스위치).
    네트워크 실패는 여기서 판정하지 않는다 — 호출 시점에 실패하면 조용히 되묻기로
    폴백한다(한국 그라운딩의 '검색 실패는 저장하지 않는다' 계약과 동일)."""
    return (os.environ.get("US_TERM_GROUNDING", "on") or "on").strip().lower() != "off"


def _sec_user_agent() -> str:
    """SEC 요청 필수 헤더 — 백필 스크립트(scripts/backfill_us_stocks.py)와 같은 값."""
    return os.environ.get(
        "SEC_USER_AGENT", "nullstock-research/1.0 (contact via https://nullstock.im)"
    )


# ─── 정본 registry(티커·이름·GICS 산업·파케이 보유) ─────────────────────────────


_REGISTRY_CACHE: Optional[tuple[float, dict[str, dict]]] = None


def _registry_by_cik() -> dict[str, dict]:
    """CIK(앞자리 0 제거) → {symbol, name, industry}. 파케이 보유 종목만.

    백테스트할 수 없는 티커는 후보에도 올리지 않는다 — 데이터 없는 종목이 테마
    유니버스에 실리면 KG 무결성 테스트가 잡기 전에 사용자 전략이 먼저 깨진다."""
    global _REGISTRY_CACHE
    try:
        mtime = _STOCKS_PATH.stat().st_mtime
    except OSError:
        return {}
    if _REGISTRY_CACHE is not None and _REGISTRY_CACHE[0] == mtime:
        return _REGISTRY_CACHE[1]
    try:
        raw = json.loads(_STOCKS_PATH.read_text())
    except (OSError, ValueError):
        return {}
    stocks = raw.get("stocks", raw) if isinstance(raw, dict) else raw
    table: dict[str, dict] = {}
    for s in stocks if isinstance(stocks, list) else []:
        symbol, cik = s.get("symbol"), s.get("cik")
        if not symbol or not cik or not (_OHLCV_DIR / f"{symbol}.parquet").exists():
            continue
        try:
            key = str(int(cik))
        except (TypeError, ValueError):
            continue
        table[key] = {
            "symbol": symbol,
            "name": s.get("name") or symbol,
            "industry": (s.get("industry") or s.get("sector") or "").strip(),
            "sector": (s.get("sector") or "").strip(),
        }
    _REGISTRY_CACHE = (mtime, table)
    return table


def _is_registry_company_name(term: str) -> bool:
    """표현이 개별 상장사 그 자체인가 — 테마 학습 차단 게이트.

    'Moderna'를 테마로 학습해 유니버스로 세우면 단일 종목 지정과 의미가 어긋난다
    (한국 그라운딩의 find_in_text 가드와 같은 계약).

    티커는 **대문자 정확 일치**일 때만 종목으로 본다 — 표기가 곧 신호다. 테마어와
    티커 철자가 겹치는 실측 사례가 있다("mrna 관련주"의 mRNA vs 모더나 티커 MRNA):
    대소문자를 뭉개면 이 테마가 영영 학습되지 않는다. 회사명은 대소문자·공백을
    무시하고 본다(표기 변형이 흔하다)."""
    registry = _registry_by_cik()
    stripped = (term or "").strip()
    if any(stripped == entry["symbol"] for entry in registry.values()):
        return True
    key = _term_key(term)
    return any(key == _term_key(entry["name"]) for entry in registry.values())


# ─── EDGAR 전문검색 ────────────────────────────────────────────────────────────


def _edgar_page(query: str, start: str, end: str, frm: int) -> Optional[dict]:
    params = urllib.parse.urlencode({
        "q": query, "forms": _FORMS, "dateRange": "custom",
        "startdt": start, "enddt": end, "from": frm,
    })
    req = urllib.request.Request(
        f"{_EDGAR_ENDPOINT}?{params}", headers={"User-Agent": _sec_user_agent()}
    )
    try:
        with urllib.request.urlopen(req, timeout=_SEARCH_TIMEOUT_S) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 — 네트워크·차단·형식 실패를 '검색 실패'로 통일
        logger.warning("EDGAR 검색 실패(%s, from=%d): %s", query, frm, exc)
        return None


def _default_search(term: str) -> Optional[dict]:
    """테마어 완전일치 구문으로 연차보고서를 검색 → {total, filings} | None(전 페이지 실패).

    filings 항목: {cik, adsh, doc, file_date, score}. score는 EDGAR 검색엔진의 관련도로,
    그 문서가 이 표현을 얼마나 다루는지를 나타낸다 — 후보 순위의 정본이다(공시 **건수**로
    줄 세우면 연차보고서를 3년치 낸 회사가 모두 동점이 돼 사실상 알파벳순이 된다).
    한 건이라도 받으면 성공으로 본다(뒤 페이지 실패는 표본 축소일 뿐 학습을 막지 않는다)."""
    today = datetime.now(timezone.utc).date()
    start = (today - timedelta(days=_LOOKBACK_DAYS)).isoformat()
    query = f'"{term}"'
    filings: list[dict] = []
    total = 0
    ok = False
    for page in range(_MAX_PAGES):
        data = _edgar_page(query, start, today.isoformat(), page * _PAGE_SIZE)
        if data is None:
            break
        ok = True
        hits_block = data.get("hits") or {}
        total = max(total, ((hits_block.get("total") or {}).get("value")) or 0)
        hits = hits_block.get("hits") or []
        for hit in hits:
            source = hit.get("_source") or {}
            doc = (hit.get("_id") or "").split(":", 1)[-1]
            for cik in source.get("ciks") or []:
                filings.append({
                    "cik": cik,
                    "adsh": source.get("adsh") or "",
                    "doc": doc,
                    "file_date": source.get("file_date"),
                    "score": hit.get("_score") or 0.0,
                })
        if len(hits) < _PAGE_SIZE:
            break
        time.sleep(_PAGE_INTERVAL_S)
    return {"total": total, "filings": filings, "observed_from": start} if ok else None


def _evidence_url(cik: str, adsh: str, doc: str) -> str:
    try:
        cik_int = str(int(cik))
    except (TypeError, ValueError):
        cik_int = str(cik)
    return _EDGAR_ARCHIVE.format(cik=cik_int, adsh=(adsh or "").replace("-", ""), doc=doc)


def _candidates(filings: list[dict]) -> list[dict]:
    """공시 목록 → 정본 후보(관련도 내림차순, 상한 _CANDIDATE_MAX).

    순위는 그 기업 공시의 **최고 관련도 점수**(EDGAR 검색엔진)이고, 지지 건수는
    **서로 다른 공시 문서 수**다 — 같은 문서가 여러 히트로 잡혀도 한 번만 센다(건수는
    순위가 아니라 verified 승격 기준). 정본 밖·파케이 없는 CIK는 여기서 사라진다
    (조용한 제외가 아니라 '백테스트 가능한 종목만 후보'라는 계약)."""
    registry = _registry_by_cik()
    support: dict[str, set[str]] = {}
    evidence: dict[str, dict[str, str]] = {}
    profile: dict[str, dict] = {}
    score: dict[str, float] = {}
    first_seen: dict[str, str] = {}
    for filing in filings:
        try:
            cik = str(int(filing.get("cik")))
        except (TypeError, ValueError):
            continue
        entry = registry.get(cik)
        if entry is None:
            continue
        adsh = filing.get("adsh") or filing.get("doc") or ""
        symbol = entry["symbol"]
        profile[symbol] = entry
        score[symbol] = max(score.get(symbol, 0.0), float(filing.get("score") or 0.0))
        filed = filing.get("file_date")
        if isinstance(filed, str) and filed:
            prior = first_seen.get(symbol)
            first_seen[symbol] = filed if prior is None else min(prior, filed)
        support.setdefault(symbol, set()).add(adsh)
        evidence.setdefault(symbol, {})[adsh] = _evidence_url(
            cik, adsh, filing.get("doc") or "")
    rows = [
        {
            "symbol": symbol,
            "name": profile[symbol]["name"],
            "industry": profile[symbol]["industry"],
            "sector": profile[symbol]["sector"],
            "support": len(accessions),
            "score": round(score[symbol], 3),
            "first_known_date": first_seen.get(symbol),
            "evidence": [evidence[symbol][a] for a in sorted(accessions)][:3],
        }
        for symbol, accessions in support.items()
    ]
    rows.sort(key=lambda r: (-r["score"], -r["support"], r["symbol"]))
    return rows[:_CANDIDATE_MAX]


# ─── LLM 소속 심사(닫힌 후보 목록) ──────────────────────────────────────────────


# 프롬프트 실측(2026-08-26, 9B): "확실하지 않으면 고르지 않는다"를 넣으면 40곳 후보에서
# 1~2곳만 고른다(mRNA에서 모더나 하나) — 최소 구성 게이트에 걸려 학습이 성립하지 않는다.
# "해당하면 모두 고른다"는 포용 지시 + 제외 사유를 예시로 못박는 형태를 쓴다.
_JUDGE_PROMPT = (
    "너는 공시 검색 결과에서 주어진 테마의 **사업을 실제로 영위하는 기업**을 골라내는 "
    "도구다.\n"
    "후보는 연차보고서(10-K·20-F) 본문에 그 표현이 등장한 기업이며, 관련도는 그 표현을 "
    "얼마나 비중 있게 다루는지를 나타내는 검색 점수다.\n"
    "회사명·산업 분류·관련도를 근거로, 그 테마가 사업의 축인 기업을 **모두** 고른다"
    "(해당하면 20곳이든 30곳이든 모두).\n"
    "제외할 것은 그 테마를 리스크 요인·일반 기술 동향으로 스치듯 언급했을 뿐인 기업이다"
    "(예: 보험사·소매업체가 \'양자컴퓨팅 위험\'을 언급).\n"
    "이것은 소속 판정이지 투자 추천이 아니다 — 유망성·전망·우열은 판단하지 않는다.\n"
    "목록에 있는 티커만 고른다. 해당 기업이 없으면 빈 배열.\n"
    '설명 없이 JSON만 출력한다. 예: {"symbols": ["AAA", "BBB", "CCC"]} 또는 {"symbols": []}'
)


def _extract_json(raw: str) -> Optional[dict]:
    match = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _is_boilerplate_term(total: int, candidates: list[dict]) -> bool:
    """이 표현이 상투어인가 — 흔하면서(①) 상위 후보의 업종이 흩어지면(②) 참.

    판정 입력은 검색 결과의 구조화된 값(전체 히트 수, 후보의 GICS 섹터)뿐이다 —
    사용자 원문도, 공시 본문도 읽지 않는다. 임계와 실측 근거는 위 상수 주석 참조."""
    if total <= _COMMON_TOTAL_HITS:
        return False  # 희소 표현 — 업종이 흩어져도 상투어가 아니다
    top = candidates[:_TOP_CONCENTRATION_N]
    if not top:
        return False
    counts: dict[str, int] = {}
    for row in top:
        key = row.get("sector") or "?"
        counts[key] = counts.get(key, 0) + 1
    share = max(counts.values()) / len(top)
    return share < _MIN_SECTOR_SHARE


def _judge_batch(term: str, batch: list[dict], chat: ChatFn) -> list[str]:
    """후보 묶음 하나를 심사한다 → 티커 목록(묶음 밖·중복은 드롭 — 닫힌 세계 게이트)."""
    lines = [f"테마: {term}", "후보(티커 | 회사명 | 산업 분류 | 관련도 | 공시 건수):"]
    lines += [
        f"{i}. {c['symbol']} | {c['name']} | {c['industry'] or '분류 없음'} | "
        f"{c['score']} | {c['support']}"
        for i, c in enumerate(batch, 1)
    ]
    data = _extract_json(chat(_JUDGE_PROMPT, "\n".join(lines), max_tokens=400)) or {}
    raw = data.get("symbols")
    allowed = {c["symbol"] for c in batch}
    picked: list[str] = []
    for symbol in raw if isinstance(raw, list) else []:
        if isinstance(symbol, str) and symbol.strip() in allowed and symbol.strip() not in picked:
            picked.append(symbol.strip())
    return picked


def _judge_members(term: str, candidates: list[dict], chat: ChatFn) -> list[str]:
    """후보를 _JUDGE_BATCH개씩 나눠 심사하고 합집합을 만든다(순서 보존).

    한 번에 40곳을 물으면 9B가 목록 앞머리 2~9곳만 고르고 나머지를 통째로 흘린다 —
    실측(2026-08-26 E2E 사고): 같은 프롬프트로 mRNA 40후보에서 확정 2곳(MRNA·BNTX)이
    나와 최소 구성 게이트에 걸렸고, "카탈로그에서 찾지 못했다"가 그대로 다시 나갔다.
    10곳씩 나누면 같은 모델·같은 프롬프트로 안정적이다(3회 반복 실측: mRNA 25/25/25,
    양자컴퓨팅 21/21/21 — 단일 호출은 2/2/2, 9/9/9). 묶음이 작을수록 "해당하는 것을
    모두 고르라"가 실제로 수행되는 과제 크기가 된다."""
    picked: list[str] = []
    for start in range(0, len(candidates), _JUDGE_BATCH):
        for symbol in _judge_batch(term, candidates[start:start + _JUDGE_BATCH], chat):
            if symbol not in picked:
                picked.append(symbol)
    return picked


# ─── 어휘집(학습 원장) ──────────────────────────────────────────────────────────


def _term_key(term: str) -> str:
    return (term or "").strip().replace(" ", "").lower()


def _load_lexicon(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_entry(path: Path, key: str, entry: dict) -> None:
    """단일 항목 저장 — 락 안에서 재로드 후 원자적 교체(동시 요청 유실 방지)."""
    with _LEXICON_LOCK:
        lexicon = _load_lexicon(path)
        lexicon[key] = entry
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(lexicon, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(path)


def _reground_ttl_days() -> float:
    try:
        return float(os.getenv("US_TERM_REGROUND_TTL_DAYS", str(_REGROUND_TTL_DAYS_DEFAULT)))
    except ValueError:
        return _REGROUND_TTL_DAYS_DEFAULT


def _entry_is_stale(entry: Optional[dict]) -> bool:
    ttl = _reground_ttl_days()
    if ttl <= 0 or not isinstance(entry, dict):
        return False
    raw = entry.get("searched_at")
    if not isinstance(raw, str) or not raw:
        return False
    try:
        searched = datetime.fromisoformat(raw)
    except ValueError:
        return False
    if searched.tzinfo is None:
        searched = searched.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - searched > timedelta(days=ttl)


def _merge_members(old: list, new: list[dict]) -> list[dict]:
    """재학습 병합 — 기존 항목의 콘솔 검토 상태(verified/rejected)를 보존하고 새 종목만
    추가한다(rejected 부활·verified 강등 금지 — 한국 _merge_entry_edges와 같은 계약)."""
    merged = [dict(m) for m in old if isinstance(m, dict) and m.get("symbol")]
    seen = {m["symbol"] for m in merged}
    return merged + [m for m in new if m["symbol"] not in seen]


def _earliest_member_date(members: list[dict]) -> Optional[str]:
    """확정 구성원 중 가장 이른 소속 관측일(없으면 None)."""
    dates = sorted(
        m["first_known_date"] for m in members
        if isinstance(m, dict) and m.get("status") == "verified" and m.get("first_known_date")
    )
    return dates[0] if dates else None


def verified_symbols(entry: Optional[dict]) -> list[str]:
    """학습 항목의 확정 구성 티커 — verified만(pending은 콘솔 승인 대기)."""
    if not isinstance(entry, dict):
        return []
    return [
        m["symbol"] for m in entry.get("members") or []
        if isinstance(m, dict) and m.get("symbol") and m.get("status") == "verified"
    ]


def lexicon_entry(term: str, lexicon_path: Optional[Path] = None) -> Optional[dict]:
    """테마어의 학습 항목(정확 일치) — 없으면 None."""
    return _load_lexicon(lexicon_path or _LEXICON_PATH).get(_term_key(term))


# ─── 공개 진입점 ────────────────────────────────────────────────────────────────


def ground_us_theme(
    term: str,
    chat: ChatFn,
    search_fn: Optional[SearchFn] = None,
    lexicon_path: Optional[Path] = None,
    on_search: Optional[Callable[[], None]] = None,
) -> Optional[tuple[str, list[str]]]:
    """카탈로그 밖 테마어를 공시 검색으로 학습한다 → (테마명, 구성 티커) | None.

    호출 계약: **US 카탈로그·시드·학습 오버레이 조회(resolve_us_theme)가 이미 실패한
    표현**만 넘어온다. 실패(구성 미달·검색 실패·소속 기업 없음)는 None이고, 그때는
    호출부의 되묻기가 그대로 표면화한다 — 조용한 확정도, 한국 체인 폴백도 없다.

    on_search는 실제 검색에 진입할 때 1회 호출된다(호출부의 '검색 중' 진행 표시).
    """
    if not term or not isinstance(term, str):
        return None
    if not grounding_available():
        return None  # 운영 스위치 off — 주입 검색(테스트·대체 소스)도 함께 막는다
    from engine.us_knowledge_graph import normalize_theme_term

    from engine.us_industry_registry import classification_label

    name = normalize_theme_term(term)
    if len(name) < 2 or _is_registry_company_name(name):
        # 개별 기업명은 테마가 아니다(단일 종목 지정 경로 소관)
        return None
    if classification_label(name) is not None:
        # [축 구분] 분류(GICS 섹터·산업)는 정본이지 관측 집합이 아니다 — 테마로 학습하면
        # 같은 표현이 두 축에 동시에 존재하게 된다. 실측 오염(2026-08-27): 축 판정이
        # 없던 QA 실행에서 'healthcare'가 공시 학습으로 21곳짜리 테마가 돼 그래프에
        # 올라갔고, 업종 필터 미지원 계약을 지키던 테스트가 깨졌다. 체인이 이미
        # 분류를 먼저 보지만(호출부), 원장은 남는 산출물이라 여기서도 막는다.
        logger.info("테마어 '%s'는 분류 라벨 — 테마로 학습하지 않음(분류 축 소관)", name)
        return None

    path = lexicon_path or _LEXICON_PATH
    key = _term_key(name)
    previous = _load_lexicon(path).get(key)
    if previous is not None and not _entry_is_stale(previous):
        # 같은 표현을 두 번 검색하지 않는다 — 성공분은 지식그래프가 이미 결정론으로
        # 해석하므로 여기 오는 건 대개 미달 항목이다(그대로 되묻기).
        symbols = verified_symbols(previous)
        return (previous.get("term", name), symbols) if len(symbols) >= _MIN_MEMBERS else None

    if on_search is not None:
        try:
            on_search()
        except Exception:  # noqa: BLE001 — 진행 표시 실패가 해석을 깨면 안 된다
            pass

    found = (search_fn or _default_search)(name)
    if found is None:
        logger.warning("테마어 '%s' 공시 검색 실패 — 저장하지 않음(복구 후 재시도 가능)", name)
        return None
    total = int(found.get("total") or 0)
    candidates = _candidates(found.get("filings") or [])
    if _is_boilerplate_term(total, candidates):
        # 선별력 없는 표현 — 공시 언급이 소속의 증거가 되지 못한다. 지어내지 않고 되묻는다.
        logger.info("테마어 '%s' 공시 %d건·상위 후보 업종 분산 — 상투어로 보고 학습하지 않음",
                    name, total)
        return None
    picked = _judge_members(name, candidates, chat) if candidates else []
    by_symbol = {c["symbol"]: c for c in candidates}
    members = [
        {
            "symbol": symbol,
            "name": by_symbol[symbol]["name"],
            "support": by_symbol[symbol]["support"],
            "score": by_symbol[symbol]["score"],
            # 소속을 처음 확인한 공시의 제출일 — 이 날짜 **이전은 모른다**(아래
            # observed_from 이전은 아예 보지 않았다). 한국 KG의 테마 엣지
            # first_known_date(뉴스 최초 보도일)와 같은 자리·같은 뜻이다.
            "first_known_date": by_symbol[symbol]["first_known_date"],
            "status": ("verified" if by_symbol[symbol]["support"] >= _AUTO_VERIFY_SUPPORT
                       else "pending"),
            "evidence": by_symbol[symbol]["evidence"],
        }
        for symbol in picked
    ]
    if previous is not None:
        members = _merge_members(previous.get("members") or [], members)
    entry = {
        "term": name,
        "members": members,
        "candidates_seen": len(candidates),
        # 테마 최초 관측일 = 확정 구성원 중 가장 이른 공시 제출일. observed_from은
        # 검색이 들여다본 창의 시작일이다 — 이 둘을 함께 두지 않으면 "3년 전부터
        # 생긴 테마"로 오독된다(창이 3년이라 모든 테마의 관측일이 그 뒤에 몰린다).
        # 소비자는 "이 날짜부터는 사실이었다"까지만 주장할 수 있다.
        "first_known_date": _earliest_member_date(members),
        "observed_from": found.get("observed_from"),
        "searched_at": datetime.now(timezone.utc).isoformat(),
        "source": "edgar:fts",
    }
    _save_entry(path, key, entry)
    symbols = verified_symbols(entry)
    logger.info(
        "테마어 학습: %s → 후보 %d곳·소속 %d곳(확정 %d곳)",
        name, len(candidates), len(members), len(symbols),
    )
    if len(symbols) < _MIN_MEMBERS:
        # 구성 미달은 테마 미성립 — 조용히 축소 반영하지 않는다(되묻기 유지)
        return None
    return name, symbols
