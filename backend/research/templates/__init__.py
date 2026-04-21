"""Strategy template catalog — deterministic DSL producers.

Each template module exposes ``build(params: dict, universe: list[str]) -> ParsedStrategy``.
The generator enumerates templates × param grid to produce candidates.
"""

from research.templates import ai_signal, mean_reversion, momentum, value, volume_breakout

TEMPLATE_REGISTRY = {
    "momentum": momentum,
    "mean_reversion": mean_reversion,
    "value": value,
    "volume_breakout": volume_breakout,
    "ai_signal": ai_signal,
}

__all__ = ["TEMPLATE_REGISTRY"]
