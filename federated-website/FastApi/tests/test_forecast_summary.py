"""FR-25: forecast summary from computed facts; Claude only when switched on."""

from app.services import forecast_summary as fs


def points(powers):
    return [{"timestamp": f"2026-11-27T{h:02d}:00:00Z", "power_kw": p} for h, p in enumerate(powers)]


def test_facts_and_template_name_the_drop(monkeypatch):
    monkeypatch.delenv("SUMMARY_LLM", raising=False)
    pts = points([40000, 42000, 45000, 30000, 12000, 8000, 6000, 7000, 9000, 10000])
    out = fs.summarize(("s", 72, "a", "r", 1), pts, "wind", 50000, 72)
    f = out["facts"]
    assert out["source"] == "rules" and f["peak_kw"] == 45000 and f["low_kw"] == 6000
    assert f["largest_change_kw"] < 0 and "drops by" in out["text"] and "45.0 MW" in out["text"]
    assert fs.summarize(("s", 72, "a", "r", 1), [], "wind", 50000, 72) is out          # cached per forecast


def test_no_power_no_summary():
    assert fs.facts([{"timestamp": "2026-11-27T00:00:00Z", "power_kw": None}], "solar", 1000, 1) is None


def test_claude_failure_falls_back_to_rules(monkeypatch):
    monkeypatch.setenv("SUMMARY_LLM", "claude")
    monkeypatch.setattr(fs, "_claude", lambda f: None)
    out = fs.summarize(("s2", 1, "b", "r", 1), points([100, 200, 300]), "solar", 1000, 1)
    assert out["source"] == "rules" and out["text"]
    monkeypatch.setattr(fs, "_claude", lambda f: "Output rises through the morning.")
    out = fs.summarize(("s3", 1, "b", "r", 1), points([100, 200, 300]), "solar", 1000, 1)
    assert out == {**out, "source": "claude", "text": "Output rises through the morning."}
