"""
LLM-based news event extractor using Qwen3.5-4B-Q4_K_M (GGUF, Metal accelerated).

Uses llama-cpp-python for fast inference (~3-5s/article on Apple Silicon).
Loaded lazily on first use and cached as a module-level singleton.
Falls back gracefully if model is unavailable or inference fails.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from typing import Optional

logger = logging.getLogger(__name__)

_GGUF_REPO = "unsloth/Qwen3.5-4B-GGUF"
_GGUF_FILE = "Qwen3.5-4B-Q4_K_M.gguf"

_lock = threading.Lock()
_model = None
_loaded = False


def _load():
    global _model, _loaded
    with _lock:
        if _loaded:
            return
        _loaded = True
        try:
            from huggingface_hub import hf_hub_download
            from llama_cpp import Llama

            logger.info("Loading %s via llama-cpp (Metal)...", _GGUF_FILE)
            gguf_path = hf_hub_download(repo_id=_GGUF_REPO, filename=_GGUF_FILE)
            _model = Llama(
                model_path=gguf_path,
                n_gpu_layers=-1,   # 전체 레이어 Metal GPU 오프로드
                n_ctx=1024,
                verbose=False,
            )
            logger.info("LLM loaded: %s", _GGUF_FILE)
        except Exception as exc:
            logger.warning("LLM load failed (%s) — falling back to rule-based", exc)
            _model = None


def is_available() -> bool:
    _load()
    return _model is not None


_PROMPT_TEMPLATE = """<|im_start|>system
You are a Korean financial news classifier. Output ONLY a JSON object, no explanation.<|im_end|>
<|im_start|>user
Classify this Korean stock news title into JSON with keys: event_type, sentiment, severity, summary.

event_type choices: earnings_beat, earnings_miss, guidance_up, guidance_down, large_contract, share_buyback, rights_offering, ceo_change, regulatory_probe, lawsuit_loss, lawsuit_win, factory_fire, product_launch, product_failure, dividend_increase, dividend_cut, mna, delisting_risk, accounting_issue, analyst_upgrade, analyst_downgrade, macro_rate, policy_change, sector_tailwind, sector_headwind, general_positive, general_negative, general_neutral
sentiment: positive | negative | neutral
severity: 0.0-1.0
summary: one Korean sentence

Title: {title}<|im_end|>
<|im_start|>assistant
<think>

</think>
"""


def extract(title: str, summary: Optional[str] = None) -> Optional[dict]:
    """
    Run GGUF inference and return structured event data.
    Returns None if LLM is unavailable or inference fails.
    """
    if not is_available():
        return None

    try:
        text = title
        if summary:
            text = f"{title} {summary[:200]}"

        prompt = _PROMPT_TEMPLATE.format(title=text)

        output = _model(
            prompt,
            max_tokens=200,
            temperature=0.0,
            stop=["<|im_end|>", "<|im_start|>"],
            echo=False,
        )
        raw = output["choices"][0]["text"].strip()

        # strip any residual think tags
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

        # find valid JSON block
        for m in reversed(list(re.finditer(r"\{[^{}]+\}", raw, re.DOTALL))):
            try:
                data = json.loads(m.group())
                if "event_type" in data and "sentiment" in data:
                    return {
                        "event_type": str(data.get("event_type", "general_neutral")),
                        "sentiment":  str(data.get("sentiment", "neutral")),
                        "severity":   float(data.get("severity", 0.3)),
                        "summary":    str(data.get("summary", title)),
                    }
            except json.JSONDecodeError:
                continue

        logger.warning("LLM output has no valid JSON: %s", raw[:200])
        return None

    except Exception as exc:
        logger.warning("LLM inference failed: %s", exc)
        return None
