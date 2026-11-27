"""
Short text summary of a forecast (requirement FR-25).

Two steps:
  1. facts()      computed here from the forecast points: peak and lowest power with their times,
                  expected energy, and the largest drop or rise, all in plant power. Always works.
  2. summarize()  writes 1-3 sentences from those facts. With SUMMARY_LLM=claude and Claude API
                  credentials (ANTHROPIC_API_KEY or an `ant auth login` profile), Claude rewords the
                  facts into plain language; otherwise, or if that call fails, a fixed template is used.
Only the computed facts (a few numbers and times) go to Claude, never a plant's measurements or
identity. Summaries are cached per forecast, so a page refresh doesn't call Claude again.
"""

import json
import logging
import os
import threading
from datetime import datetime
from typing import Optional

log = logging.getLogger("fedwind.summary")

MODEL = os.environ.get("SUMMARY_MODEL", "claude-opus-5-5")
_cache: dict = {}
_lock = threading.Lock()
_CACHE_MAX = 500


def _fmt_power(kw: float) -> str:
    return f"{kw / 1000:.1f} MW" if abs(kw) >= 1000 else f"{kw:.0f} kW"


def _when(ts: str) -> str:
    try:
        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return t.strftime("%a %H:%M UTC")
    except ValueError:
        return ts


def facts(points: list, energy_type: str, capacity_kw: Optional[float], horizon: int) -> Optional[dict]:
    """Numbers the summary rests on; None when the forecast has no power values."""
    pts = [p for p in points if p.get("power_kw") is not None]
    if not pts:
        return None
    powers = [float(p["power_kw"]) for p in pts]
    hi, lo = max(range(len(pts)), key=powers.__getitem__), min(range(len(pts)), key=powers.__getitem__)
    # Largest change within any 6-hour span, to name a drop or a ramp
    span, best = min(6, len(pts) - 1), (0.0, 0, 0)
    for i in range(len(pts) - span):
        d = powers[i + span] - powers[i]
        if abs(d) > abs(best[0]):
            best = (d, i, i + span)
    cap = float(capacity_kw or 0)
    return {
        "energy_type": energy_type, "horizon_h": horizon, "hours": len(pts), "capacity_kw": cap or None,
        "start": pts[0]["timestamp"], "end": pts[-1]["timestamp"],
        "peak_kw": round(powers[hi], 1), "peak_at": pts[hi]["timestamp"],
        "low_kw": round(powers[lo], 1), "low_at": pts[lo]["timestamp"],
        "mean_capacity_factor": round(sum(powers) / len(powers) / cap, 3) if cap else None,
        "energy_mwh": round(sum(powers) / 1000, 1),       # hourly points: kW x 1 h
        "largest_change_kw": round(best[0], 1), "change_from": pts[best[1]]["timestamp"],
        "change_to": pts[best[2]]["timestamp"],
    }


def template(f: dict) -> str:
    """The fixed wording (no model involved)."""
    out = [f"Over the next {f['hours']} hours output peaks at {_fmt_power(f['peak_kw'])} around {_when(f['peak_at'])}"
           f" and is lowest, {_fmt_power(f['low_kw'])}, around {_when(f['low_at'])}."]
    cap = f.get("capacity_kw")
    change = f["largest_change_kw"]
    if cap and abs(change) >= 0.2 * cap:
        word = "drops" if change < 0 else "rises"
        out.append(f"It {word} by {_fmt_power(abs(change))} between {_when(f['change_from'])} and {_when(f['change_to'])}.")
    if f.get("mean_capacity_factor") is not None:
        out.append(f"Expected energy: {f['energy_mwh']:g} MWh, {f['mean_capacity_factor']:.0%} of capacity on average.")
    return " ".join(out)


def _claude(f: dict) -> Optional[str]:
    """Claude rewords the facts; None on any problem (the template is used then)."""
    try:
        import anthropic
    except ImportError:
        return None
    try:
        client = anthropic.Anthropic(timeout=20.0, max_retries=1)
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=1024,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=("You write the short summary shown under a power forecast on an energy website for plant "
                    "operators. Use only the facts given, in at most three plain sentences; say when output "
                    "is expected to drop or peak. No advice, no greeting, no markdown. Times are UTC."),
            messages=[{"role": "user", "content": json.dumps(f)}],
        )
    except anthropic.APIError as e:
        log.warning("forecast summary via Claude failed: %s", e)
        return None
    if response.stop_reason == "refusal":
        return None
    text = " ".join(b.text for b in response.content if b.type == "text").strip()
    return text or None


def summarize(key: tuple, points: list, energy_type: str, capacity_kw: Optional[float], horizon: int) -> Optional[dict]:
    """{"text", "source": "claude" | "rules", "facts"} for one forecast; cached by key."""
    with _lock:
        if key in _cache:
            return _cache[key]
    f = facts(points, energy_type, capacity_kw, horizon)
    if f is None:
        return None
    text, source = None, "rules"
    if os.environ.get("SUMMARY_LLM", "off").lower() == "claude":
        text = _claude(f)
        source = "claude" if text else "rules"
    out = {"text": text or template(f), "source": source, "facts": f}
    with _lock:
        if len(_cache) >= _CACHE_MAX:
            _cache.clear()
        _cache[key] = out
    return out
