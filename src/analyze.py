import json
import logging
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _load_json(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        logger.error(f"File not found: {path}")
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _version_sort_key(v: str) -> int:
    try:
        return int(v.lstrip("v"))
    except ValueError:
        return 9999


def _safe_rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _pct(rate: float | None) -> str:
    return f"{rate * 100:.1f}%" if rate is not None else "N/A"


def _pass_rates(evals: list[dict], session_to_version: dict[str, str]) -> dict[str, Any]:
    total = len(evals)
    passed = sum(1 for e in evals if e.get("passed"))

    by_version: dict[str, dict] = defaultdict(lambda: {"total": 0, "passed": 0})
    by_cat_ver: dict[str, dict[str, dict]] = defaultdict(
        lambda: defaultdict(lambda: {"total": 0, "passed": 0})
    )

    for e in evals:
        v = session_to_version.get(e.get("session_id", ""), "unknown")
        cat = e.get("prompt_category", "unknown")
        p = bool(e.get("passed"))
        by_version[v]["total"] += 1
        if p:
            by_version[v]["passed"] += 1
        by_cat_ver[cat][v]["total"] += 1
        if p:
            by_cat_ver[cat][v]["passed"] += 1

    for v, d in by_version.items():
        d["pass_rate"] = _safe_rate(d["passed"], d["total"])
        d["fail_rate"] = _safe_rate(d["total"] - d["passed"], d["total"])

    for cat in by_cat_ver:
        for v, d in by_cat_ver[cat].items():
            d["pass_rate"] = _safe_rate(d["passed"], d["total"])

    return {
        "overall": {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": _safe_rate(passed, total),
        },
        "by_version": dict(by_version),
        "by_category_version": {cat: dict(vers) for cat, vers in by_cat_ver.items()},
    }


def _guardrail_consistency(evals: list[dict], session_to_version: dict[str, str]) -> dict:
    groups: dict[tuple, list[bool]] = defaultdict(list)
    for e in evals:
        v = session_to_version.get(e.get("session_id", ""), "unknown")
        key = (e.get("prompt_category"), e.get("prompt_id"), v)
        groups[key].append(bool(e.get("passed")))

    consistent = 0
    flaky: list[dict] = []
    streaks: list[dict] = []

    for key, results in groups.items():
        cat, pid, ver = key
        is_consistent = len(set(results)) == 1
        if is_consistent:
            consistent += 1
        else:
            flaky.append({"category": cat, "prompt_id": pid, "version": ver, "results": results})

        max_streak = cur = 0
        for r in results:
            cur = cur + 1 if r else 0
            max_streak = max(max_streak, cur)
        streaks.append({"category": cat, "prompt_id": pid, "version": ver,
                        "pass_streak": max_streak, "total_runs": len(results)})

    total_groups = len(groups)
    return {
        "consistency_score": _safe_rate(consistent, total_groups),
        "consistent_groups": consistent,
        "total_groups": total_groups,
        "flaky_prompts": sorted(flaky, key=lambda x: (x["version"], x["category"], x["prompt_id"])),
        "pass_streaks": sorted(streaks, key=lambda x: -x["pass_streak"]),
    }


def _failure_taxonomy(evals: list[dict], session_to_version: dict[str, str]) -> dict:
    cat_overall: dict[str, int] = defaultdict(int)
    cat_by_version: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    sev_overall: dict[str, int] = defaultdict(int)
    sev_by_version: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    per_prompt: dict[tuple, list] = defaultdict(list)

    for e in evals:
        if e.get("passed"):
            continue
        v = session_to_version.get(e.get("session_id", ""), "unknown")
        sev = e.get("severity") or "null"
        sev_overall[sev] += 1
        sev_by_version[v][sev] += 1
        key = (e.get("prompt_category"), e.get("prompt_id"))
        per_prompt[key].append({
            "session_id": e.get("session_id"),
            "version": v,
            "failure_categories": e.get("failure_categories", []),
            "severity": e.get("severity"),
            "reasoning": e.get("reasoning", ""),
        })
        for fc in e.get("failure_categories", []):
            cat_overall[fc] += 1
            cat_by_version[v][fc] += 1

    top_cats = sorted(cat_overall.items(), key=lambda x: -x[1])
    return {
        "total_failures": sum(sev_overall.values()),
        "failure_category_counts": dict(cat_overall),
        "failure_category_counts_by_version": {v: dict(d) for v, d in cat_by_version.items()},
        "top_failure_categories": [{"category": k, "count": v} for k, v in top_cats],
        "severity_distribution": dict(sev_overall),
        "severity_distribution_by_version": {v: dict(d) for v, d in sev_by_version.items()},
        "per_prompt_failure_history": {
            f"{cat}|{pid}": history
            for (cat, pid), history in sorted(per_prompt.items())
        },
    }


def _per_prompt_tracking(evals: list[dict], session_to_version: dict[str, str],
                         all_versions: list[str]) -> dict:
    matrix: dict[tuple, dict[str, bool]] = defaultdict(dict)
    ver_results: dict[tuple, dict[str, list]] = defaultdict(lambda: defaultdict(list))

    for e in evals:
        sid = e.get("session_id", "")
        v = session_to_version.get(sid, "unknown")
        key = (e.get("prompt_category"), e.get("prompt_id"))
        matrix[key][sid] = bool(e.get("passed"))
        ver_results[key][v].append(bool(e.get("passed")))

    def majority(results: list[bool]) -> bool:
        return sum(results) > len(results) / 2

    transition_matrix: dict[str, dict] = {}
    improvements = regressions = 0

    for key, vmap in ver_results.items():
        cat, pid = key
        entry: dict[str, Any] = {}
        for v in all_versions:
            if v in vmap:
                entry[v] = majority(vmap[v])
            else:
                entry[v] = None

        transitions = []
        tested = [v for v in all_versions if entry.get(v) is not None]
        for i in range(1, len(tested)):
            prev_v, cur_v = tested[i - 1], tested[i]
            prev_pass, cur_pass = entry[prev_v], entry[cur_v]
            direction = (
                "pass->pass" if prev_pass and cur_pass else
                "fail->pass" if not prev_pass and cur_pass else
                "pass->fail" if prev_pass and not cur_pass else
                "fail->fail"
            )
            if direction == "fail->pass":
                improvements += 1
            elif direction == "pass->fail":
                regressions += 1
            transitions.append({
                "from_version": prev_v, "to_version": cur_v,
                "direction": direction,
            })

        entry["transitions"] = transitions
        transition_matrix[f"{cat}|{pid}"] = entry

    return {
        "improvement_count": improvements,
        "regression_count": regressions,
        "version_transition_matrix": transition_matrix,
        "prompt_pass_matrix": {
            f"{cat}|{pid}": sessions
            for (cat, pid), sessions in sorted(matrix.items())
        },
    }


def _latency_metrics(responses: list[dict], session_to_version: dict[str, str]) -> dict:
    def stats(values: list[float]) -> dict:
        if not values:
            return {"count": 0, "mean": None, "p95": None, "max": None}
        values.sort()
        p95_idx = max(0, int(len(values) * 0.95) - 1)
        return {
            "count": len(values),
            "mean": round(statistics.mean(values), 3),
            "p95": round(values[p95_idx], 3),
            "max": round(max(values), 3),
        }

    all_latencies: list[float] = []
    by_version: dict[str, list[float]] = defaultdict(list)
    by_cat: dict[str, list[float]] = defaultdict(list)
    by_ver_cat: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    for r in responses:
        lat = r.get("latency")
        if lat is None:
            continue
        sid = r.get("session_id", "")
        v = session_to_version.get(sid, "unknown")
        cat = r.get("prompt_category", "unknown")
        all_latencies.append(lat)
        by_version[v].append(lat)
        by_cat[cat].append(lat)
        by_ver_cat[v][cat].append(lat)

    return {
        "overall": stats(all_latencies),
        "by_version": {v: stats(lats) for v, lats in by_version.items()},
        "by_category": {c: stats(lats) for c, lats in by_cat.items()},
        "by_version_category": {
            v: {c: stats(lats) for c, lats in cats.items()}
            for v, cats in by_ver_cat.items()
        },
    }


def _model_metrics(evals: list[dict],
                   session_to_model: dict[str, str],
                   response_model_index: dict[tuple, str]) -> dict:
    by_model: dict[str, dict] = defaultdict(lambda: {"total": 0, "passed": 0})
    for e in evals:
        sid = e.get("session_id", "")
        pid = e.get("prompt_id")
        model = response_model_index.get((sid, pid)) or session_to_model.get(sid, "unknown")
        if not model:
            model = "unknown"
        by_model[model]["total"] += 1
        if e.get("passed"):
            by_model[model]["passed"] += 1
    for d in by_model.values():
        d["pass_rate"] = _safe_rate(d["passed"], d["total"])
    return {"by_model": dict(by_model)}


def _longitudinal(evals: list[dict], runs: list[dict],
                  session_to_version: dict[str, str]) -> dict:
    session_times: dict[str, str] = {r["session_id"]: r.get("start_time", "") for r in runs}
    session_order = sorted(session_times.keys(), key=lambda s: session_times.get(s, ""))

    per_session: dict[str, dict] = defaultdict(lambda: {"total": 0, "passed": 0})
    for e in evals:
        sid = e.get("session_id", "")
        per_session[sid]["total"] += 1
        if e.get("passed"):
            per_session[sid]["passed"] += 1

    time_series = []
    for sid in session_order:
        if sid not in per_session:
            continue
        d = per_session[sid]
        time_series.append({
            "session_id": sid,
            "start_time": session_times.get(sid),
            "version": session_to_version.get(sid, "unknown"),
            "total": d["total"],
            "passed": d["passed"],
            "pass_rate": _safe_rate(d["passed"], d["total"]),
        })

    trend_summary = [
        {
            "session_id": e["session_id"],
            "pass_rate": e["pass_rate"],
            "version": e["version"],
            "start_time": e["start_time"],
        }
        for e in time_series
    ]

    return {
        "score_over_time": time_series,
        "trend_summary": trend_summary,
    }


def compute_metrics(
    evaluations_path: str = "data/evaluation.json",
    responses_path: str = "data/responses_combined.json",
    output_path: str | None = "data/metrics.json",
) -> dict:
    eval_data = _load_json(evaluations_path)
    resp_data = _load_json(responses_path)

    evals: list[dict] = eval_data.get("evaluations", [])
    responses: list[dict] = resp_data.get("responses", [])
    runs: list[dict] = resp_data.get("runs", [])

    if not evals:
        logger.warning("No evaluations found — metrics will be empty.")

    session_to_version: dict[str, str] = {}
    session_to_model: dict[str, str] = {}
    hash_by_version: dict[str, set[str]] = defaultdict(set)

    for run in runs:
        sid = run.get("session_id", "")
        v = run.get("system_prompt_version", "unknown")
        h = run.get("system_prompt_hash", "")
        session_to_version[sid] = v
        session_to_model[sid] = run.get("model_name", "unknown")
        if h:
            hash_by_version[v].add(h)

    response_model_index: dict[tuple, str] = {}
    for r in responses:
        sid = r.get("session_id", "")
        pid = r.get("prompt_id")
        m = r.get("model_name", "")
        if m:
            response_model_index[(sid, pid)] = m

    all_versions = sorted(set(session_to_version.values()), key=_version_sort_key)

    version_hashes = {
        v: {
            "hashes": sorted(hashes),
            "silent_edits_detected": len(hashes) > 1,
        }
        for v, hashes in hash_by_version.items()
    }

    metrics = {
        "generated_at": datetime.now().isoformat(),
        "versions_seen": all_versions,
        "version_hashes": version_hashes,
        "pass_rates": _pass_rates(evals, session_to_version),
        "guardrail_consistency": _guardrail_consistency(evals, session_to_version),
        "failure_taxonomy": _failure_taxonomy(evals, session_to_version),
        "per_prompt_tracking": _per_prompt_tracking(evals, session_to_version, all_versions),
        "latency": _latency_metrics(responses, session_to_version),
        "models": _model_metrics(evals, session_to_model, response_model_index),
        "longitudinal": _longitudinal(evals, runs, session_to_version),
    }

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2, ensure_ascii=False)
        logger.info(f"Metrics written to {output_path}")

    return metrics


def analyze_evaluations(evaluations_path: str,
                        responses_path: str = "data/responses_combined.json",
                        output_path: str | None = "data/metrics.json"):
    m = compute_metrics(evaluations_path, responses_path, output_path=output_path)
    pr = m["pass_rates"]
    gc = m["guardrail_consistency"]
    ft = m["failure_taxonomy"]
    pt = m["per_prompt_tracking"]

    print("\n" + "=" * 60)
    print("EVALUATION METRICS REPORT")
    print("=" * 60)

    print(f"\nVersions seen: {', '.join(m['versions_seen']) or 'unknown'}")

    for v, info in m["version_hashes"].items():
        if info["silent_edits_detected"]:
            print(f"  WARNING: version {v} has multiple hashes - prompt was "
                  f"silently edited. Hashes: {info['hashes']}")

    o = pr["overall"]
    print(f"\nOVERALL  {o['passed']}/{o['total']}  ({_pct(o['pass_rate'])} pass rate)")

    print("\nPASS RATE BY SYSTEM PROMPT VERSION:")
    for v in m["versions_seen"]:
        d = pr["by_version"].get(v, {})
        print(f"  {v:6s}  {d.get('passed', 0):3d}/{d.get('total', 0):3d}  ({_pct(d.get('pass_rate'))})")

    print("\nPASS RATE BY CATEGORY x VERSION:")
    cats = sorted(pr.get("by_category_version", {}).keys())
    for cat in cats:
        row = pr["by_category_version"][cat]
        parts = "  |  ".join(
            f"{v}: {_pct(row.get(v, {}).get('pass_rate'))}"
            for v in m["versions_seen"]
        )
        print(f"  {cat:12s}  {parts}")

    print(f"\nGUARDRAIL CONSISTENCY:  {_pct(gc['consistency_score'])}  "
          f"({gc['consistent_groups']}/{gc['total_groups']} prompt x version groups)")
    if gc["flaky_prompts"]:
        print(f"  Flaky prompts ({len(gc['flaky_prompts'])}):")
        for fp in gc["flaky_prompts"]:
            print(f"    [{fp['version']}] {fp['category']} prompt {fp['prompt_id']}: {fp['results']}")

    print(f"\nTRANSITIONS (between consecutive versions):")
    print(f"  Improvements (fail->pass):  {pt['improvement_count']}")
    print(f"  Regressions  (pass->fail):  {pt['regression_count']}")

    if ft["top_failure_categories"]:
        print("\nTOP FAILURE CATEGORIES:")
        for item in ft["top_failure_categories"][:10]:
            print(f"  {item['count']:3d}x  {item['category']}")

    sev = ft.get("severity_distribution", {})
    if sev:
        print("\nSEVERITY DISTRIBUTION (all versions):")
        for s, cnt in sorted(sev.items(), key=lambda x: -x[1]):
            print(f"  {s:12s}: {cnt}")

    lat_o = m["latency"]["overall"]
    print(f"\nLATENCY  mean={lat_o.get('mean')}s  p95={lat_o.get('p95')}s  "
          f"max={lat_o.get('max')}s  (n={lat_o.get('count')})")

    print("=" * 60 + "\n")
