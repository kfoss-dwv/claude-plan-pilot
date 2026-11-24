#!/usr/bin/env python3
"""Average eval runs from results.jsonl. Usage: aggregate.py [--label L] [--sha S] [--last N] [--json]"""
import argparse
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
NUM = ("total_tokens", "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens",
       "cost_usd", "duration_s", "turns", "tool_uses", "deviations", "script_exceptions", "check_errors_seen", "md_bytes", "html_bytes")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label")
    ap.add_argument("--sha")
    ap.add_argument("--last", type=int)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    rows = [json.loads(ln) for ln in (HERE / "results.jsonl").read_text().splitlines() if ln.strip()]
    if a.label:
        rows = [r for r in rows if r.get("label") == a.label]
    if a.sha:
        rows = [r for r in rows if str(r.get("sha", "")).startswith(a.sha)]
    if a.last:
        rows = rows[-a.last:]
    out = {"runs": len(rows),
           "check_ok": sum(1 for r in rows if r.get("check_ok")),
           "served": sum(1 for r in rows if r.get("served")),
           "runs_with_deviations": sum(1 for r in rows if r.get("deviations")),
           "adapters": {k: sum(1 for r in rows if r.get("adapter") == k) for k in {r.get("adapter") for r in rows}}}
    for k in NUM:
        vals = [r[k] for r in rows if isinstance(r.get(k), (int, float))]
        if vals:
            out[k] = {"mean": round(statistics.mean(vals), 3), "min": min(vals), "max": max(vals),
                      "stdev": round(statistics.stdev(vals), 3) if len(vals) > 1 else 0}
    if a.json:
        print(json.dumps(out, indent=2))
        return
    print(f"runs {out['runs']} · check ok {out['check_ok']} · served {out['served']} · runs with deviations {out['runs_with_deviations']} · adapters {out['adapters']}")
    for k in NUM:
        if k in out:
            v = out[k]
            print(f"  {k:30} mean {v['mean']:>12}  min {v['min']:>10}  max {v['max']:>10}  sd {v['stdev']}")


if __name__ == "__main__":
    main()
