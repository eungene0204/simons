import os
import sys
import time
from pathlib import Path

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import nl_cache


def test_nl_cache_key_changes_when_universe_file_changes(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    stocks = data_dir / "korea-stocks.json"
    kospi200 = data_dir / "kospi200-cache.json"
    stocks.write_text("[]", encoding="utf-8")
    kospi200.write_text('{"symbols":[]}', encoding="utf-8")

    monkeypatch.setattr(nl_cache, "_BASE_DIR", tmp_path)
    monkeypatch.setattr(
        nl_cache,
        "_UNIVERSE_FILES",
        (stocks, kospi200),
    )

    key_before = nl_cache.nl_cache_key("prompt", "mlx", None, None)
    time.sleep(0.001)
    stocks.write_text('[{"symbol":"005930"}]', encoding="utf-8")
    key_after = nl_cache.nl_cache_key("prompt", "mlx", None, None)

    assert key_before != key_after
