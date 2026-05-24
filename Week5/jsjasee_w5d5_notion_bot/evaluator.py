import gradio as gr
import pandas as pd

from evaluation.eval import load_and_evaluate

MRR_GREEN, MRR_AMBER = 0.8, 0.5
NDCG_GREEN, NDCG_AMBER = 0.8, 0.5
RECALL_GREEN, RECALL_AMBER = 80.0, 60.0
COVERAGE_GREEN, COVERAGE_AMBER = 80.0, 60.0
ANSWER_GREEN, ANSWER_AMBER = 4.5, 3.0
METRICS = [
    ("mrr", "MRR", "mrr", 3, "", [0, 1]),
    ("ndcg", "nDCG", "ndcg", 3, "", [0, 1]),
    ("recall_at_k", "Recall@k", "recall", 1, "%", [0, 100]),
    ("keyword_coverage", "Keyword Coverage", "coverage", 1, "%", [0, 100]),
    ("accuracy", "Accuracy", "answer", 2, "", [1, 5]),
    ("completeness", "Completeness", "completeness", 2, "", [1, 5]),
    ("relevance", "Relevance", "answer", 2, "", [1, 5]),
]
REFUSAL_CARD = ("refusal_correct", "Refusal Correct", "binary", 2, "", [0, 1])

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
    if metric_type == "coverage":
        return (
            "green"
            if value >= COVERAGE_GREEN
            else "orange"
            if value >= COVERAGE_AMBER
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
    if metric_type == "binary":
        return "green" if value >= 1.0 else "red"
    return "gray"


def build_metric_cards(summary: dict) -> list[str]:
    """Build color-coded headline metric cards from the overall eval summary."""
    overall = summary["overall"]
    cards = []
    # if suffix is %, means we add a % at the back
    for key, label, metric_type, precision, suffix, _ in [*METRICS, REFUSAL_CARD]:
        value = (
            overall[key] * 100 if key in {"recall_at_k"} else overall[key]
        )  # note that keyword coverage already returns the normal percentage, so no need to include it in {"recall_at_k", "keyword_coverage"}
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
                        value * 100
                        if key
                        in {
                            "recall_at_k"
                        }  # no need * 100 for "keyword_coverage" since it already returns percentages.
                        else value,
                        precision,
                    ),
                }
            )
        frames[key] = pd.DataFrame(rows)
    return frames


def run_eval(k: int, progress=gr.Progress()) -> tuple[object, ...]:
    """Execute evals and return dashboard-ready card HTML plus plot data."""
    summary = load_and_evaluate(k=int(k), progress=progress)
    cards = build_metric_cards(summary)
    frames = build_category_frames(summary)
    outputs = []
    for card, (key, *_rest) in zip(cards, METRICS):
        outputs.extend([card, frames[key]])
    outputs.append(cards[-1])
    return tuple(outputs)


def build_ui():
    """Build the standalone Gradio dashboard for eval runs."""
    with gr.Blocks(title="Notion Notes Evals") as app:
        gr.Markdown(
            "# Notion Notes Evals\nRun the current eval set and inspect per-category results."
        )
        with gr.Row():
            k_value = gr.Slider(label="Top K", minimum=1, maximum=20, step=1, value=10)
            run_button = gr.Button("Run Evals", variant="primary")
        refusal_card = gr.HTML()
        outputs = []
        for key, label, _, _, _, y_lim in METRICS:
            with gr.Row():
                card = gr.HTML()
                plot = gr.BarPlot(
                    x="Category",
                    y=label,
                    y_lim=y_lim,
                    title=f"{label} by Category",
                    height=280,
                )
            outputs.extend([card, plot])
        run_button.click(fn=run_eval, inputs=k_value, outputs=[*outputs, refusal_card])
    return app


if __name__ == "__main__":
    build_ui().launch(inbrowser=True)
