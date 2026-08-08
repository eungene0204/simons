"""
KIS(한국투자증권) 종목마스터에서 지수 구성종목 명부를 읽는다.

왜 KIS 마스터인가 — 2026-08-07 조사에서 다른 경로는 전부 막혀 있었다:
  - KRX 정보데이터시스템(pykrx / FinanceDataReader / 직접 호출): 세션은 열리지만
    데이터 조회 bld 는 모두 `LOGOUT` 400 을 반환한다.
  - KRX Open API: "코스닥 150" 지수의 **가격**만 제공하고 구성종목 서비스가 없다.
  - 네이버 entryJongmok: code 파라미터와 무관하게 항상 KOSPI200 만 반환하고,
    영숫자 신규 상장 코드(0126Z0)를 누락해 수동 보정이 필요했다.
KIS 마스터는 인증 없이 받을 수 있고 두 지수를 모두 담으며 영숫자 코드도 포함한다.

편입 플래그 위치는 문서가 아니라 실측으로 특정했다(고정폭 블록의 Y/N·코드 컬럼을
전수 조사해 개수가 정의와 일치하는 컬럼을 찾는 방식):
  - kospi_code.mst  꼬리 228B 중 idx 19 가 KOSPI200 섹터업종 코드 — '0'이 아닌 값 정확히 200개.
    바로 옆 idx 20(KOSPI100, 100개)·21(KOSPI50, 50개)·22(KRX300, 297개)가 KIS 문서상
    필드 순서와 일치하고, KOSPI50 ⊂ KOSPI100 ⊂ KOSPI200 포함관계도 성립한다.
  - kosdaq_code.mst 꼬리 222B 중 idx 36 이 KOSDAQ150 편입 Y/N — Y 정확히 150개.

**검증을 통과하지 못하면 명부를 돌려주지 않는다.** 잘못된 명부는 조용히 잘못된
유니버스로 백테스트·자동매매를 돌린다(FR-VM-073 이 막으려는 사고).
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Callable, NamedTuple

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_STOCKS_PATH = _PROJECT_ROOT / "data" / "korea-stocks.json"
_MASTER_URL = "https://new.real.download.dws.co.kr/common/master/{name}.mst.zip"
_DOWNLOAD_TIMEOUT = 60


class MasterLayoutError(RuntimeError):
    """마스터 레이아웃이 기대와 다르다 — 명부를 신뢰할 수 없다."""


class IndexSpec(NamedTuple):
    master: str            # KIS 마스터 파일 이름
    tail_width: int        # 레코드 끝 고정폭 블록 길이
    offset: int            # 그 블록 안에서 편입 플래그 위치
    is_member: Callable[[str], bool]
    market: str            # 편입 종목이 속해야 하는 시장
    size: int              # 지수 정의상 종목 수
    tolerance: int         # 정기변경 과도기 허용 오차


INDEX_SPECS: dict[str, IndexSpec] = {
    "kospi200": IndexSpec(
        master="kospi_code",
        tail_width=228,
        offset=19,
        is_member=lambda char: char not in ("0", " "),
        market="KOSPI",
        size=200,
        tolerance=5,
    ),
    "kosdaq150": IndexSpec(
        master="kosdaq_code",
        tail_width=222,
        offset=36,
        is_member=lambda char: char == "Y",
        market="KOSDAQ",
        size=150,
        tolerance=5,
    ),
}


def download_master(name: str) -> str:
    import requests

    response = requests.get(_MASTER_URL.format(name=name), timeout=_DOWNLOAD_TIMEOUT)
    response.raise_for_status()
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    return archive.read(f"{name}.mst").decode("cp949")


def parse_members(text: str, spec: IndexSpec) -> list[tuple[str, str]]:
    """(종목코드, 종목명) 목록. 검증 실패 시 MasterLayoutError."""
    members: list[tuple[str, str]] = []
    for line in text.splitlines():
        if len(line) <= spec.tail_width:
            continue
        head, tail = line[: -spec.tail_width], line[-spec.tail_width :]
        if spec.is_member(tail[spec.offset]):
            members.append((head[0:9].strip(), head[21:].strip()))
    _validate(members, spec)
    return members


def _validate(members: list[tuple[str, str]], spec: IndexSpec) -> None:
    count = len(members)
    if abs(count - spec.size) > spec.tolerance:
        raise MasterLayoutError(
            f"편입 종목 {count}개 — 기대({spec.size}±{spec.tolerance}) 밖. "
            "KIS 마스터 레이아웃이 바뀌었을 수 있다."
        )

    malformed = [symbol for symbol, _ in members if len(symbol) != 6]
    if malformed:
        raise MasterLayoutError(f"종목코드 형식 이상: {malformed[:10]}")

    stocks = json.loads(_STOCKS_PATH.read_text(encoding="utf-8"))
    listed = {item["symbol"] for item in stocks if item.get("market") == spec.market}
    outside = [symbol for symbol, _ in members if symbol not in listed]
    if outside:
        raise MasterLayoutError(
            f"{spec.market} 소속이 아닌 종목 {len(outside)}건: {outside[:10]} — "
            "플래그 위치를 잘못 읽었을 가능성이 높다."
        )


def fetch_index_members(index_id: str) -> list[tuple[str, str]]:
    """지수 구성종목을 KIS 마스터에서 내려받아 검증 후 반환."""
    spec = INDEX_SPECS[index_id]
    return parse_members(download_master(spec.master), spec)
