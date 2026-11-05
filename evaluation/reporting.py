import json
from html import escape
from pathlib import Path
from uuid import uuid4

from evaluation.models import EvaluationRun


def write_atomic(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    scratch = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        scratch.write_text(content, encoding="utf-8")
        scratch.replace(path)
    finally:
        scratch.unlink(missing_ok=True)


def display(value) -> str:
    if value is None:
        return "Not evaluated"
    if isinstance(value, float):
        return f"{value:.4g}"
    if isinstance(value, list | dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def sections(run: EvaluationRun):
    summary = run.summary
    yield (
        "Run",
        ("Setting", "Value"),
        [
            ("Decision", run.decision),
            ("Run ID", run.run_id),
            ("Timestamp (UTC)", run.timestamp),
            ("Git commit", run.git_sha),
            ("Dataset", run.dataset_version),
            ("Dataset fingerprint", run.dataset_fingerprint),
            ("Comparison key", run.comparison_key),
            ("Approved baseline", run.baseline_run_id),
            *sorted(run.config.items()),
        ],
    )
    yield (
        "Quality gates",
        ("Gate", "Decision", "Explanation"),
        [(gate.name, gate.status, gate.reason) for gate in run.gates],
    )
    yield (
        "Quality metrics",
        ("Framework and metric", "Mean", "SD", "Min", "Max", "Scored", "Status counts"),
        [
            (
                name,
                row["mean"],
                row["stddev"],
                row["min"],
                row["max"],
                row["count"],
                row["statuses"],
            )
            for name, row in sorted(summary["metrics"].items())
        ],
    )
    yield (
        "Behavior and safety",
        ("Measurement", "Value"),
        [
            (name.replace("_", " ").capitalize(), summary[name])
            for name in (
                "golden_behavior_rate",
                "conversation_pass_rate",
                "hallucination_rate",
                "hallucination_evaluated",
                "hallucination_cutoff",
                "safety_pass_rate",
                "injection_success_rate",
                "synthetic_leakage_rate",
                "false_refusal_rate",
            )
        ],
    )
    yield (
        "Safety category results",
        ("Category", "Executed", "Passed", "Markers", "Leaks", "Fixture exposures"),
        [
            (
                name,
                row["executed"],
                row["passed"],
                row["marker_seen"],
                row["leaked"],
                row["fixtures_exposed"],
            )
            for name, row in sorted(summary["safety_categories"].items())
        ],
    )
    yield (
        "Latency and generation cost",
        ("Measurement", "Observations or value", "p50", "p95"),
        [
            (key, summary[key]["count"], summary[key]["p50"], summary[key]["p95"])
            for key in (
                "request_latency_ms",
                "retrieval_latency_ms",
                "generation_latency_ms",
                "judge_latency_ms",
            )
        ]
        + [
            ("Trials", summary["request_count"], None, None),
            ("Trial execution error rate", summary["error_rate"], None, None),
            ("Estimated generation USD", summary["estimated_generation_usd"], None, None),
            (
                "Measured generation cost observations",
                summary["estimated_cost_samples"],
                None,
                None,
            ),
        ],
    )
    yield (
        "Judge comparison",
        (
            "Case",
            "Trial",
            "Metric",
            "DeepEval",
            "Ragas",
            "Ragas minus DeepEval",
            "Method difference",
        ),
        [
            (
                row["case_id"],
                row["repetition"],
                row["metric"],
                row["deepeval"],
                row["ragas"],
                row["ragas_minus_deepeval"],
                row["method_difference"],
            )
            for row in run.comparisons
        ],
    )
    prompt = run.promptfoo
    yield (
        "Promptfoo comparison",
        ("Prompt or case", "Results"),
        (
            [
                *sorted(prompt["prompts"].items()),
                ("Grounded minus baseline pass rate", prompt["grounded_minus_baseline_pass_rate"]),
                *sorted(prompt["cases"].items()),
            ]
            if prompt
            else []
        ),
    )
    yield (
        "Repeatability by case",
        ("Case", "Trials", "Failed or errored", "Unique answers", "p95 ms"),
        [
            (
                case,
                item["observations"],
                item["failures"],
                item["unique_responses"],
                item["latency_ms"]["p95"],
            )
            for case, item in sorted(summary["repeatability"].items())
        ],
    )
    yield (
        "Case regressions",
        ("Case", "Metric", "Baseline", "Current", "Deterioration"),
        [
            (row["case_id"], row["metric"], row["baseline"], row["current"], row["deterioration"])
            for row in run.regressions
        ],
    )
    yield (
        "Failed cases and execution errors",
        ("Case", "Trial", "Status", "Reason"),
        [
            (t.case_id, t.repetition, t.status, t.reason)
            for t in run.trials
            if t.status in {"fail", "error"}
        ]
        + [
            (t.case_id, t.repetition, "judge error", f"{m.framework}.{m.metric} / {m.reason}")
            for t in run.trials
            for m in t.metrics
            if m.status == "error"
        ]
        + [("Run", None, "error", error) for error in run.errors],
    )
    yield (
        "Engineering actions",
        ("Observed issue", "Action"),
        [
            (
                gate.name,
                {
                    "ERROR": "Inspect dependency readiness and per-trial error codes before rerunning.",
                    "INCONCLUSIVE": "Collect missing observations or load an approved compatible baseline.",
                    "FAIL": "Inspect failed trials and compare their retrieval, citations, and judge reasons.",
                }[gate.status],
            )
            for gate in run.gates
            if gate.status != "PASS"
        ],
    )


def markdown_cell(value) -> str:
    return escape(display(value)).replace("|", "&#124;").replace("\n", " ")


def render_markdown(run: EvaluationRun) -> str:
    lines = [
        "# AI Quality Suite evaluation",
        "",
        "Full trial responses and scores are in the JSON report.",
    ]
    for title, columns, rows in sections(run):
        lines.extend(["", f"## {title}", ""])
        if not rows:
            lines.append("No observations recorded.")
            continue
        lines.append("| " + " | ".join(columns) + " |")
        lines.append("| " + " | ".join("---" for _ in columns) + " |")
        lines.extend("| " + " | ".join(map(markdown_cell, row)) + " |" for row in rows)
    return "\n".join(lines) + "\n"


def render_html(run: EvaluationRun) -> str:
    parts = [
        """<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>AI Quality Suite evaluation</title>
<style>
:root{color-scheme:light;--ink:#17283b;--paper:#f4f7fb;--line:#dce5ef;--accent:#244f86}
body{font:15px/1.55 system-ui,sans-serif;color:var(--ink);background:var(--paper);margin:0}
main{max-width:1280px;margin:auto;padding:2.5rem 1.5rem} h1{font-size:2.4rem;margin:.25rem 0}
header{background:#152d4b;color:white;padding:1.7rem 2rem;border-radius:12px}
header p{color:#c6d9ec} section{padding:1rem 1.3rem;background:white;margin:1rem 0;border-radius:10px}
h2{font-size:1.2rem;color:var(--accent);margin:.3rem 0 .8rem} .scroll{overflow:auto}
table{width:100%;border-collapse:collapse;text-align:left} th{background:#eaf1fa}
td,th{padding:.5rem .65rem;border-bottom:1px solid var(--line);vertical-align:top;overflow-wrap:anywhere}
tr:nth-child(even){background:#f7faff}
</style><body><main><header><h1>AI Quality Suite</h1>
<p>RAG evaluation, safety observations, and release gates</p>""",
        f"<strong>{escape(run.decision)}</strong></header>",
    ]
    for title, columns, rows in sections(run):
        parts.append(f"<section><h2>{escape(title)}</h2>")
        if rows:
            parts.append(
                '<div class="scroll"><table><thead><tr>'
                + "".join(f'<th scope="col">{escape(col)}</th>' for col in columns)
                + "</tr></thead><tbody>"
            )
            parts.extend(
                "<tr>" + "".join(f"<td>{escape(display(v))}</td>" for v in row) + "</tr>"
                for row in rows
            )
            parts.append("</tbody></table></div>")
        else:
            parts.append("<p>No observations recorded.</p>")
        parts.append("</section>")
    parts.append("</main></body></html>")
    return "\n".join(parts)


def write_reports(run: EvaluationRun, directory: Path):
    stem = run.timestamp.replace(":", "").replace("+", "_") + "-" + run.run_id
    if not all(char.isalnum() or char in "-_." for char in stem):
        raise ValueError("Unsafe report identifier")
    artifacts = {
        "json": json.dumps(run.model_dump(mode="json") | {"decision": run.decision}, indent=2),
        "md": render_markdown(run),
        "html": render_html(run),
    }
    for ext, content in artifacts.items():
        write_atomic(directory / f"{stem}.{ext}", content)
        write_atomic(directory / f"latest.{ext}", content)
