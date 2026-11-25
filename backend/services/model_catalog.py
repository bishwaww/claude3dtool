"""
Live Claude model discovery + per-model request shaping.

- list_models(): GET /v1/models via the official SDK (auto-paginated), cached for
  10 minutes per API key, with an offline fallback list.
- request_options(): builds the thinking / effort / fallback kwargs that are valid
  for the chosen model, so switching models in the UI never produces a 400.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, Optional

import anthropic

from config import FALLBACK_MODELS, decorate_model

_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_TTL_SEC = 600


async def list_models(api_key: str, force: bool = False) -> dict[str, Any]:
    """Returns {"models": [...], "source": "live" | "fallback", "error": str | None}."""
    if not api_key:
        return {
            "models": [decorate_model(m) for m in FALLBACK_MODELS],
            "source": "fallback",
            "error": "No Anthropic API key configured.",
        }

    key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
    cached = _CACHE.get(key_hash)
    if cached and not force and (time.time() - cached[0]) < _TTL_SEC:
        return {"models": cached[1], "source": "live", "error": None}

    try:
        client = anthropic.AsyncAnthropic(api_key=api_key)
        models: list[dict[str, Any]] = []
        async for m in client.models.list(limit=100):
            entry: dict[str, Any] = {
                "id": m.id,
                "display_name": getattr(m, "display_name", None) or m.id,
                "created_at": str(getattr(m, "created_at", "") or ""),
                "max_input_tokens": getattr(m, "max_input_tokens", None),
                "max_tokens": getattr(m, "max_tokens", None),
            }
            models.append(decorate_model(entry))
        # Newest first (the API already returns newest first; keep it stable).
        models.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        _CACHE[key_hash] = (time.time(), models)
        return {"models": models, "source": "live", "error": None}
    except anthropic.AuthenticationError:
        err = "Anthropic API key was rejected (401)."
    except anthropic.APIConnectionError:
        err = "Could not reach api.anthropic.com (offline?)."
    except anthropic.APIStatusError as e:
        err = f"Models API error {e.status_code}: {e.message}"
    return {
        "models": [decorate_model(m) for m in FALLBACK_MODELS],
        "source": "fallback",
        "error": err,
    }


# ------------------------------------------------------------------------------
# Per-model request shaping
# ------------------------------------------------------------------------------

# Models that still use the legacy `{"type": "enabled", "budget_tokens": N}` thinking
# and do not accept `output_config.effort` reliably.
_LEGACY_PREFIXES = (
    "claude-3",
    "claude-haiku-4-5",
    "claude-sonnet-4-5",
    "claude-sonnet-4-0",
    "claude-sonnet-4-2",  # claude-sonnet-4-20250514
    "claude-opus-4-5",
    "claude-opus-4-1",
    "claude-opus-4-0",
    "claude-opus-4-2",  # claude-opus-4-20250514
)

# Models where `display` is opt-in (default "omitted") and xhigh effort exists.
_NO_XHIGH_PREFIXES = ("claude-opus-4-6", "claude-sonnet-4-6")

# Models that support the server-side refusal fallback (beta) with fallbacks="default".
_FALLBACK_PREFIXES = (
    "claude-fable-5-2",
    "claude-fable-5-1",
    "claude-opus-5-5",
    "claude-opus-5",
    "claude-sonnet-5-5",
)
FALLBACK_BETA = "server-side-fallback-2026-07-01"

VALID_EFFORTS = ("low", "medium", "high", "xhigh", "max")


def is_legacy(model: str) -> bool:
    return model.startswith(_LEGACY_PREFIXES)


def supports_fallbacks(model: str) -> bool:
    return model.startswith(_FALLBACK_PREFIXES)


def request_options(model: str, *, thinking: bool, effort: Optional[str]) -> dict[str, Any]:
    """
    kwargs for messages.stream(): thinking / output_config.

    thinking=True  → visible (summarized) adaptive thinking at the chosen effort.
    thinking=False → no thinking param. On always-thinking models (Opus 5.5, Fable)
                     this still runs adaptive thinking, so effort drops to "low" to
                     keep it short and cheap.
    """
    opts: dict[str, Any] = {}
    if is_legacy(model):
        if thinking:
            opts["thinking"] = {"type": "enabled", "budget_tokens": 8000}
        return opts

    eff = effort if effort in VALID_EFFORTS else "high"
    if model.startswith(_NO_XHIGH_PREFIXES) and eff == "xhigh":
        eff = "high"

    if thinking:
        if model.startswith(_NO_XHIGH_PREFIXES):
            opts["thinking"] = {"type": "adaptive"}
        else:
            opts["thinking"] = {"type": "adaptive", "display": "summarized"}
        opts["output_config"] = {"effort": eff}
    elif model.startswith(_ALWAYS_THINKING_PREFIXES):
        # Thinking can't be fully switched off here; low effort keeps it minimal.
        opts["output_config"] = {"effort": "low"}
    else:
        # Omitting `thinking` disables it on these models; keep the chosen effort.
        opts["output_config"] = {"effort": eff}
    return opts


# Models where omitting `thinking` still runs adaptive thinking.
_ALWAYS_THINKING_PREFIXES = (
    "claude-fable-",
    "claude-mythos-",
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-haiku-5",
)
