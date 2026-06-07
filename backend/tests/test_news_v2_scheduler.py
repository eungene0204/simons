"""Tests for news_v2 scheduler startup collection target selection."""

import os
import sys
from dataclasses import dataclass

import pytest

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from news_v2 import config
from news_v2 import scheduler


@dataclass(frozen=True)
class _DummySettings:
    enabled: bool = True
    startup_collect_enabled: bool = True
    bootstrap_symbols: list[str] = None  # type: ignore[assignment]
    bootstrap_collect_limit: int = 3

    def __post_init__(self):
        if self.bootstrap_symbols is None:
            object.__setattr__(self, "bootstrap_symbols", ["005930", "000660", "005930", "035420"])


class _Repo:
    def __init__(self, tiers):
        self.tiers = tiers

    async def list_symbols_in_tier(self, tier: int, limit: int = 500):
        return list(self.tiers.get(tier, []))[:limit]


@pytest.mark.asyncio
async def test_startup_symbols_fall_back_to_bootstrap_list(monkeypatch):
    monkeypatch.setattr(scheduler, "get_settings", lambda: _DummySettings())

    symbols = await scheduler._resolve_startup_symbols(_Repo({}))

    assert symbols == ["005930", "000660", "035420"]


@pytest.mark.asyncio
async def test_startup_symbols_prefer_priority_tiers(monkeypatch):
    monkeypatch.setattr(
        scheduler,
        "get_settings",
        lambda: _DummySettings(bootstrap_symbols=["005930"], bootstrap_collect_limit=4),
    )

    symbols = await scheduler._resolve_startup_symbols(
        _Repo({1: ["HIGH", "MED"], 2: ["LOW", "HIGH"], 3: ["TAIL"]})
    )

    assert symbols == ["HIGH", "MED", "LOW", "TAIL"]


def test_env_list_parses_comma_separated_values(monkeypatch):
    monkeypatch.setenv("NEWSV2_BOOTSTRAP_SYMBOLS", "005930, 000660,,035420 ")

    assert config.Settings().bootstrap_symbols == ["005930", "000660", "035420"]
