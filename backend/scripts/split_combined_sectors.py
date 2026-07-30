"""묶음 섹터 분할 — 'A/B' 한 섹터를 A·B 두 독립 섹터로 나눈다(FR-STR-066 후속).

분할 대상은 **KSIC 산업분류가 두 갈래를 깨끗하게 가르는 6쌍만**이다. 나머지 12쌍
(에너지/원자력·미디어/엔터·기계/장비 등)은 산업분류가 구분을 주지 않거나 두 낱말이
포함·동의 관계라 분할하지 않는다 — 근거 없는 종목 귀속을 만들지 않기 위함이다.

멱등하다. 이미 분할된 데이터에 다시 돌리면 변경 0으로 끝난다.

    python backend/scripts/split_combined_sectors.py [--apply]

--apply 없이 실행하면 변경 계획만 출력한다(dry-run).
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
KOREA_STOCKS = REPO / "data" / "korea-stocks.json"
STOCK_MASTER = REPO / "data" / "stock-master.json"

# 구 섹터 → (신규 섹터 A, 신규 섹터 B). B는 아래 KSIC 목록에 걸리는 종목, A는 나머지.
# "나머지=A" 규칙을 쓰는 이유: 분류가 애매한 종목을 새 섹터로 밀어넣지 않고, 원래 섹터의
# 주된 성격(다수파)에 남겨 두기 위함이다.
SPLITS: dict[str, tuple[str, str]] = {
    "증권/보험": ("증권", "보험"),
    "은행/금융지주": ("금융지주", "은행"),
    "조선/해운": ("조선", "해운"),
    "식품/음료": ("식품", "음료"),
    "소프트웨어/플랫폼": ("소프트웨어", "플랫폼"),
    "사료/축산": ("사료", "축산"),
    "화장품/패션": ("패션", "화장품"),
    "디스플레이/부품": ("전자부품", "디스플레이"),
}
# ── 디스플레이/부품 분할 (2026-07-30) ──────────────────────────────────────────
# 이 섹터는 131/132가 KSIC '전자부품 제조업' 한 코드라 분류로는 갈리지 않는다.
# 디스플레이 귀속은 **외부 큐레이션 카탈로그**(네이버·주달 디스플레이 테마 ∩ 이 섹터)를
# 근거로 삼고, 카탈로그가 놓친 명백한 건만 근거를 적어 보강한다. 나머지는 전자부품이다
# (PCB·MLCC·카메라모듈·커넥터·안테나·반도체 부자재 등 — 디스플레이와 무관).
DISPLAY_SYMBOLS: dict[str, str] = {
    "034220": "디스플레이",  # LG디스플레이
    "213420": "디스플레이",  # 덕산네오룩스
    "484120": "디스플레이",  # 도우인시스
    "067770": "디스플레이",  # 세진티에스
    "149950": "디스플레이",  # 아바텍
    "059100": "디스플레이",  # 아이컴포넌트
    "073110": "디스플레이",  # 엘엠에스
    "155650": "디스플레이",  # 와이엠씨
    "069330": "디스플레이",  # 유아이디
    "179900": "디스플레이",  # 유티아이
    "191410": "디스플레이",  # 육일씨엔에쓰
    "272290": "디스플레이",  # 이녹스첨단소재
    "037330": "디스플레이",  # 인지디스플레
    "051370": "디스플레이",  # 인터플렉스
    "094970": "디스플레이",  # 제이엠티
    "177830": "디스플레이",  # 파버나인
    "049120": "디스플레이",  # 파인디앤씨
    "371950": "디스플레이",  # 풍원정밀
    "347770": "디스플레이",  # 핌스
    "054040": "디스플레이",  # 한국컴퓨터
    # 카탈로그 누락 — 명시 보강
    "148150": "디스플레이",  # 세경하이테크 — 디스플레이 보호·데코필름
    "090460": "디스플레이",  # 비에이치 — OLED용 FPCB
    "441270": "디스플레이",  # 파인엠텍 — 폴더블 디스플레이 힌지·내장재
    "042600": "디스플레이",  # 새로닉스 — 디스플레이 BLU 부품
    "418420": "디스플레이",  # 라온텍 — 마이크로디스플레이(LCoS·OLEDoS)
}


# 두 파일의 industry 어휘가 다르다 — korea-stocks.json은 KSIC 정식 명칭
# ('보험업'), stock-master.json은 거래소 축약 분류('보험'). 한 테이블로 처리하면
# 상폐 보험사(메리츠화재·KB손해보험 등)가 증권으로 잘못 넘어간다(실측).

# B쪽으로 보낼 KSIC 산업분류(korea-stocks.json). 여기 없으면 A쪽이다.
B_INDUSTRIES: dict[str, frozenset[str]] = {
    # 보험사만 분리 — 증권·자산운용·캐피탈·창투는 모두 증권(금융투자)에 남는다.
    "증권/보험": frozenset({"보험업", "보험 및 연금관련 서비스업", "재 보험업"}),
    # 은행·저축은행만 은행 — 지주사(KB금융·신한지주 등)는 금융지주.
    "은행/금융지주": frozenset({"은행 및 저축기관"}),
    # 해상운송만 해운 — 조선소와 조선 지주(HD한국조선해양)는 조선.
    "조선/해운": frozenset({"해상 운송업"}),
    # 주류·비주류 음료 제조만 음료.
    "식품/음료": frozenset({"알코올음료 제조업", "비알코올음료 및 얼음 제조업"}),
    # 포털·정보매개·정보서비스가 플랫폼, 패키지/게임 등 개발·공급은 소프트웨어.
    "소프트웨어/플랫폼": frozenset({
        "자료처리, 호스팅, 포털 및 기타 인터넷 정보매개 서비스업",
        "기타 정보 서비스업",
    }),
    # 도축·육류가공만 축산 — 배합사료·곡물가공·농축산물 도매는 사료.
    "사료/축산": frozenset({"도축, 육류 가공 및 저장 처리업"}),
    # KSIC에 화장품 코드가 없다. 화장품사는 '기타 화학제품 제조업'으로 등록돼 있고,
    # 이 섹터에 그 코드로 들어와 있는 종목은 OVERRIDDEN_SYMBOLS로 귀속한 화장품사뿐이다
    # (나머지는 전부 봉제의복·직물·가죽 등 섬유·의류 코드 → 패션).
    "화장품/패션": frozenset({"기타 화학제품 제조업"}),
    # 디스플레이는 산업분류로 안 갈린다 — DISPLAY_SYMBOLS(카탈로그 근거)가 가른다.
    "디스플레이/부품": frozenset(),
}

# B쪽으로 보낼 거래소 축약 분류(stock-master.json — 상폐 종목 백필분).
# '금융'(165건)은 대부분 스팩(159건)이라 증권에 남긴다 — 이 버킷에 보험사는 없음을 확인했다.
B_INDUSTRIES_MASTER: dict[str, frozenset[str]] = {
    "증권/보험": frozenset({"보험"}),
    "은행/금융지주": frozenset({"은행"}),
    "조선/해운": frozenset({"운송·창고"}),
    "식품/음료": frozenset(),          # '음식료·담배' 한 버킷뿐 — 사명 단위로만 가른다
    "소프트웨어/플랫폼": frozenset({"인터넷"}),
    "사료/축산": frozenset(),
    "화장품/패션": frozenset(),   # 상폐분은 전부 '섬유·의류' → 패션
    "디스플레이/부품": frozenset(),
}

# 분류 어휘가 두 갈래를 못 가르는 개별 종목의 수동 귀속.
# 근거 없는 추정은 넣지 않는다 — 여기 없으면 A쪽(다수파)에 남는다.
MANUAL_OVERRIDES: dict[str, str] = {
    **DISPLAY_SYMBOLS,
    "000895": "음료",  # 보해양조우 — stock-master는 '음식료·담배' 한 버킷이라 주류를 못 가름
}


def resolve(sector: str, industry: str | None, symbol: str, table: dict) -> str:
    if symbol in MANUAL_OVERRIDES:
        return MANUAL_OVERRIDES[symbol]
    side_a, side_b = SPLITS[sector]
    return side_b if (industry or "") in table[sector] else side_a


def migrate(rows: list[dict], label: str, table: dict) -> tuple[int, list[str]]:
    changed = 0
    no_industry: list[str] = []
    tally: collections.Counter = collections.Counter()
    for row in rows:
        sector = row.get("sector")
        if sector not in SPLITS:
            continue
        if not row.get("industry"):
            no_industry.append(f"{row.get('symbol')} {row.get('name')} ({sector})")
        new = resolve(sector, row.get("industry"), row.get("symbol", ""), table)
        row["sector"] = new
        tally[f"{sector} → {new}"] += 1
        changed += 1
    if tally:
        print(f"\n[{label}] {changed}종목 재분류")
        for key, count in sorted(tally.items()):
            print(f"   {count:5d}  {key}")
    else:
        print(f"\n[{label}] 변경 없음 (이미 분할됨)")
    return changed, no_industry


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="실제로 파일에 쓴다")
    args = parser.parse_args()

    korea = json.loads(KOREA_STOCKS.read_text(encoding="utf-8"))
    korea_rows = korea if isinstance(korea, list) else korea["stocks"]
    master = json.loads(STOCK_MASTER.read_text(encoding="utf-8"))

    total = 0
    orphans: list[str] = []
    for rows, label, table in (
        (korea_rows, "korea-stocks.json", B_INDUSTRIES),
        (master["stocks"], "stock-master.json", B_INDUSTRIES_MASTER),
    ):
        changed, no_industry = migrate(rows, label, table)
        total += changed
        orphans.extend(no_industry)

    if orphans:
        print(f"\n⚠ industry 없음 — 다수파 섹터로 귀속됨 ({len(orphans)}건, 검토 요망)")
        for line in orphans:
            print(f"   {line}")

    if not args.apply:
        print(f"\n[dry-run] 총 {total}종목이 바뀝니다. 실제 반영은 --apply")
        return 0

    KOREA_STOCKS.write_text(
        json.dumps(korea, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    STOCK_MASTER.write_text(
        json.dumps(master, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\n✅ 총 {total}종목 반영 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
