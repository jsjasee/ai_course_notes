import gradio as gr

from answer import answer_question
from ingest import sync_notion_notes

APP_CSS = """
:root {
    --page-bg: linear-gradient(180deg, #f7f1e8 0%, #efe7db 100%);
    --panel-bg: rgba(255, 252, 247, 0.88);
    --panel-alt: rgba(245, 237, 223, 0.95);
    --border: #d7c6af;
    --ink: #2f2419;
    --muted: #6f5b48;
    --accent: #a45a3f;
}

@media (prefers-color-scheme: dark) {
    :root {
        --page-bg: linear-gradient(180deg, #16120f 0%, #221a16 100%);
        --panel-bg: rgba(34, 26, 22, 0.9);
        --panel-alt: rgba(44, 34, 29, 0.95);
        --border: #5a4638;
        --ink: #f6eadb;
        --muted: #c4ae97;
        --accent: #e39a72;
    }
}

:root[data-theme="light"] {
    --page-bg: linear-gradient(180deg, #f7f1e8 0%, #efe7db 100%);
    --panel-bg: rgba(255, 252, 247, 0.88);
    --panel-alt: rgba(245, 237, 223, 0.95);
    --border: #d7c6af;
    --ink: #2f2419;
    --muted: #6f5b48;
    --accent: #a45a3f;
}

:root[data-theme="dark"] {
    --page-bg: linear-gradient(180deg, #16120f 0%, #221a16 100%);
    --panel-bg: rgba(34, 26, 22, 0.9);
    --panel-alt: rgba(44, 34, 29, 0.95);
    --border: #5a4638;
    --ink: #f6eadb;
    --muted: #c4ae97;
    --accent: #e39a72;
}

.gradio-container {
    background: var(--page-bg);
    color: var(--ink);
    font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", serif;
}

#app-shell {
    max-width: 1180px;
    margin: 0 auto;
}

.hero, .control-bar, .panel-card, .composer {
    background: var(--panel-bg);
    border: 1px solid var(--border);
    border-radius: 22px;
    box-shadow: 0 18px 50px rgba(84, 58, 32, 0.08);
}

.hero { padding: 8px 10px; }
.control-bar, .composer { padding: 8px; }
.panel-card { padding: 10px; min-height: 560px; }
.sources-card { background: var(--panel-alt); }

.hero h1, .panel-card label, .control-bar label, .composer label {
    color: var(--ink) !important;
}

.hero p { color: var(--muted); }
.panel-card .prose, .panel-card .md, .panel-card .message { color: var(--ink); }
.sources-card a { color: var(--accent); }
button.primary { background: var(--accent) !important; border: none !important; }
#theme-toggle {
    min-width: 9rem;
    align-self: end;
}
"""

APP_HEAD = """
<script>
const THEME_KEY = "notion-notes-theme";

function applyTheme(theme) {
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
  localStorage.setItem(THEME_KEY, theme);
  const toggle = document.getElementById("theme-toggle-btn");
  if (toggle) toggle.textContent = theme === "dark" ? "Use Light Mode" : "Use Dark Mode";
}

function cycleTheme() {
  const current = localStorage.getItem(THEME_KEY) || "system";
  applyTheme(current === "dark" ? "light" : "dark");
}

document.addEventListener("DOMContentLoaded", () => {
  applyTheme(localStorage.getItem(THEME_KEY) || "system");
});
</script>
"""


def chat_reply(message, history):
    """Append one grounded answer to the chat history.

    Args:
        message: Latest user question.
        history: Existing Gradio chat history.

    Returns:
        Updated chat history, cleared input value, and rendered sources markdown.
    """
    history = history or []  # ensures 'history' is a usable list instead of None
    answer_md, sources_md = answer_question(
        message, history=list(history)
    )  # here we are only passing in the old copy/SNAPSHOT of the history, list(history), without the latest user message

    # updated_history is purely to update Gradio's UI (separating this for ease of reference, not compulsory)
    updated_history = list(
        history
    )  # then we are saving another copy of the history, and then adding the latest user question/message with LLM answer. this avoids changing the same list object that was passed into answer_question()
    updated_history.append({"role": "user", "content": message})
    updated_history.append({"role": "assistant", "content": answer_md})
    return updated_history, "", sources_md


def build_ui():
    """Build the Gradio app for syncing notes and chatting over them.

    Returns:
        Configured `gr.Blocks` app instance.
    """
    with gr.Blocks(title="Notion Notes Assistant", css=APP_CSS, head=APP_HEAD) as app:
        with gr.Column(elem_id="app-shell"):
            gr.Markdown(
                """
            # Notion Notes Assistant
            Sync your Notion notes into Chroma, then chat with answers grounded in your notes.
            """,
                elem_classes="hero",
            )

            with gr.Row(elem_classes="control-bar"):
                notebook_filter = gr.Textbox(
                    label="Notebook Filter",
                    placeholder="Optional notebook page ID",
                    scale=3,
                )
                max_notes = gr.Number(
                    label="Max Notes", value=100, minimum=1, precision=0
                )
                sync_button = gr.Button("Sync Notion", variant="primary")
                gr.HTML(
                    '<button id="theme-toggle-btn" class="lg secondary" '
                    'onclick="cycleTheme()">Use Dark Mode</button>',
                    elem_id="theme-toggle",
                )

            with gr.Row():
                sync_status = gr.Textbox(
                    label="Sync Status", interactive=False, lines=4
                )

            with gr.Row():
                chatbot = gr.Chatbot(
                    label="Chat",
                    type="messages",
                    height=520,
                    elem_classes="panel-card",
                )
                sources_output = gr.Markdown(
                    label="Sources", elem_classes="panel-card sources-card"
                )

            with gr.Row(elem_classes="composer"):
                question = gr.Textbox(
                    label="Message",
                    placeholder="Ask something about your notes...",
                    lines=2,
                    scale=5,
                )
                ask_button = gr.Button("Send", variant="primary", scale=1)
                clear_button = gr.Button("Clear", scale=1)

        sync_button.click(
            fn=sync_notion_notes,
            inputs=[notebook_filter, max_notes],
            outputs=sync_status,
        )
        ask_button.click(
            fn=chat_reply,
            inputs=[question, chatbot],
            outputs=[chatbot, question, sources_output],
        )
        question.submit(
            fn=chat_reply,
            inputs=[question, chatbot],
            outputs=[chatbot, question, sources_output],
        )
        clear_button.click(
            lambda: ([], "", ""), outputs=[chatbot, question, sources_output]
        )

    return app


if __name__ == "__main__":
    build_ui().launch(inbrowser=True)
