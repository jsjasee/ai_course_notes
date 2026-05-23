import gradio as gr

from evaluation.eval import load_and_evaluate


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
        gr.Markdown("# Notion Notes Evals\nRun the current eval set and inspect per-category results.")
        with gr.Row():
            k_value = gr.Slider(label="Top K", minimum=1, maximum=20, step=1, value=10)
            run_button = gr.Button("Run Evals", variant="primary")
        summary = gr.Markdown()
        breakdown = gr.Dataframe(
            headers=[
                "category", "count", "mrr", "ndcg", "recall_at_k",
                "keyword_coverage", "accuracy", "completeness",
                "relevance", "refusal_correct",
            ],
            interactive=False,
        )
        run_button.click(fn=run_eval, inputs=k_value, outputs=[summary, breakdown])
    return app


if __name__ == "__main__":
    build_ui().launch(inbrowser=True)
