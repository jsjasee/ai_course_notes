import gradio as gr
import pandas as pd

from evaluation.eval import load_and_evaluate

MRR_GREEN, MRR_AMBER = 0.8, 0.5
NDCG_GREEN, NDCG_AMBER = 0.8, 0.5
RECALL_GREEN, RECALL_AMBER = 80.0, 60.0
ANSWER_GREEN, ANSWER_AMBER = 4.5, 3.0
METRICS = [
    ("mrr", "MRR", "mrr", 3, "", [0, 1]),
    ("ndcg", "nDCG", "ndcg", 3, "", [0, 1]),
    ("recall_at_k", "Recall@k", "recall", 1, "%", [0, 100]),
    ("accuracy", "Accuracy", "answer", 2, "", [1, 5]),
    ("completeness", "Completeness", "completeness", 2, "", [1, 5]),
]

# each tuple in the metrics is saying: (metric_key, display_label, color_type, decimals, suffix, y_limit)
# eg. for recall@k, the first item is the key to read from the summary dict (see build_metric_cards function), second is the label etc.


def get_color(metric_type: str, value: float) -> str:
    """Return the card color for a metric based on the configured thresholds."""
    if metric_type == "mrr":
        return (
            "green" if value >= MRR_GREEN else "orange" if value >= MRR_AMBER else "red"
        )
    if metric_type == "ndcg":
        return (
            "green"
            if value >= NDCG_GREEN
            else "orange"
            if value >= NDCG_AMBER
            else "red"
        )
    if metric_type == "recall":
        return (
            "green"
            if value >= RECALL_GREEN
            else "orange"
            if value >= RECALL_AMBER
            else "red"
        )
    if metric_type in {"answer", "completeness"}:
        return (
            "green"
            if value >= ANSWER_GREEN
            else "orange"
            if value >= ANSWER_AMBER
            else "red"
        )
    return "gray"


def build_metric_cards(summary: dict) -> list[str]:
    """Build color-coded headline metric cards from the overall eval summary."""
    overall = summary["overall"]
    cards = []
    # if suffix is %, means we add a % at the back
    for key, label, metric_type, precision, suffix, _ in METRICS:
        value = overall[key] * 100 if key == "recall_at_k" else overall[key]
        cards.append(
            "<div style='padding:16px;border-radius:12px;background:"
            f"{get_color(metric_type, value)};color:white'>"
            f"<div style='font-size:14px'>{label}</div>"
            f"<div style='font-size:28px;font-weight:700'>{value:.{precision}f}{suffix}</div>"
            "</div>"
        )
    return cards


def build_category_frames(summary: dict) -> dict[str, pd.DataFrame]:
    """Build one per-category DataFrame per dashboard metric."""
    categories = [name for name in summary if name != "overall"]
    frames = {}
    for key, label, _, precision, _, _ in METRICS:
        rows = []
        for category in categories:
            value = summary[category][key]
            rows.append(
                {
                    "Category": category,
                    label: round(
                        value * 100 if key == "recall_at_k" else value, precision
                    ),
                }
            )
        frames[key] = pd.DataFrame(rows)
    return frames


def _format_summary(summary: dict) -> tuple[str, list[list[object]]]:
    """Turn aggregated eval metrics into markdown plus table rows."""
    overall = summary["overall"]
    lines = [
        f"- Tests: {overall['count']}",
        f"- MRR: {overall['mrr']:.3f}",
        f"- nDCG: {overall['ndcg']:.3f}",
        f"- Recall@k: {overall['recall_at_k']:.3f}",
        f"- Keyword coverage: {overall['keyword_coverage']:.1f}%",
        f"- Accuracy: {overall['accuracy']:.2f}",
        f"- Completeness: {overall['completeness']:.2f}",
        f"- Relevance: {overall['relevance']:.2f}",
        f"- Refusal correctness: {overall['refusal_correct']:.2f}",
    ]
    rows = []
    for category, metrics in summary.items():
        if category == "overall":
            continue
        rows.append(
            [
                category,
                metrics["count"],
                round(metrics["mrr"], 3),
                round(metrics["ndcg"], 3),
                round(metrics["recall_at_k"], 3),
                round(metrics["keyword_coverage"], 1),
                round(metrics["accuracy"], 2),
                round(metrics["completeness"], 2),
                round(metrics["relevance"], 2),
                round(metrics["refusal_correct"], 2),
            ]
        )
    return "\n".join(lines), rows


def run_eval(k: int) -> tuple[str, list[list[object]]]:
    """Execute the eval harness and format the result for Gradio."""
    return _format_summary(load_and_evaluate(k=int(k)))


def build_ui():
    """Build the standalone Gradio dashboard for eval runs."""
    with gr.Blocks(title="Notion Notes Evals") as app:
        gr.Markdown(
            "# Notion Notes Evals\nRun the current eval set and inspect per-category results."
        )
        with gr.Row():
            k_value = gr.Slider(label="Top K", minimum=1, maximum=20, step=1, value=10)
            run_button = gr.Button("Run Evals", variant="primary")
        summary = gr.Markdown()
        breakdown = gr.Dataframe(
            headers=[
                "category",
                "count",
                "mrr",
                "ndcg",
                "recall_at_k",
                "keyword_coverage",
                "accuracy",
                "completeness",
                "relevance",
                "refusal_correct",
            ],
            interactive=False,
        )
        run_button.click(fn=run_eval, inputs=k_value, outputs=[summary, breakdown])
    return app


if __name__ == "__main__":
    build_ui().launch(inbrowser=True)
