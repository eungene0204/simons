"""
Provider 공통 인터페이스 및 데이터 모델
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Optional
import time


@dataclass
class StockQuote:
    """종목 시세 데이터 통합 모델"""
    symbol: str
    name: str
    date: str
    open: int
    high: int
    low: int
    close: int
    volume: int
    source: str       # "kis", "naver", "yfinance", "pykrx", "krx_api"
    timestamp: float   # time.time() when fetched
    prev_close: int = 0    # 전일종가
    change_rate: float = 0.0  # 전일 대비 등락률 % (provider가 직접 제공 시 사용)
    per: Optional[float] = None   # PER (주가수익비율)
    pbr: Optional[float] = None   # PBR (주가순자산비율)
    eps: Optional[float] = None   # EPS (주당순이익)
    bps: Optional[float] = None   # BPS (주당순자산)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProviderHealth:
    """Provider 상태 정보"""
    name: str
    available: bool
    configured: bool
    latency_ms: float = 0.0
    error_count: int = 0
    last_error: Optional[str] = None
    last_success: Optional[float] = None
    disabled_until: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


class BaseProvider(ABC):
    """데이터 Provider 추상 인터페이스"""

    name: str = "base"

    @abstractmethod
    async def get_price(self, symbol: str) -> Optional[StockQuote]:
        """단일 종목 현재가 조회"""
        ...

    @abstractmethod
    async def get_prices(self, symbols: list[str]) -> dict[str, StockQuote]:
        """여러 종목 현재가 일괄 조회"""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """연결 상태 확인"""
        ...

    def is_configured(self) -> bool:
        """필요한 설정(환경변수 등)이 갖춰져 있는지 확인"""
        return True
