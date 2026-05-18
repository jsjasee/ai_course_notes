<aside>
📄

**Aligned to:** Week 5 Major Challenge — assemble files → vectorize in Chroma → conversational AI.

**Stack decision:** all Python; use [`notion-to-md-py`](https://github.com/SwordAndTea/notion-to-md-py) (port of Node's popular `notion-to-md`, MIT, last push 11 May 2026). Smoke-tested on a sample page — converts cleanly and preserves cross-page links as Markdown links (correct MVP behavior: linked pages either get indexed independently or stay out of scope).

**Packages used:** https://github.com/ramnes/notion-sdk-py & https://github.com/SwordAndTea/notion-to-md-py

</aside>

### What it is

A local Gradio app that turns my own Notion study notes into a conversational knowledge worker. The MVP queries one Notion Notes database (filtered to a single notebook via `notion-client`), converts each selected page to Markdown via `notion-to-md-py`, indexes the Markdown in ChromaDB, and answers questions with grounded source chunks linking back to the original Notion pages.

### Success Criteria

- [ ] App syncs 20–50 pages from one Notion Notes database into local Markdown files.
- [ ] App rebuilds a single ChromaDB collection named `notion_notes` from those files.
- [ ] User can ask a natural-language question and get an LLM answer grounded in retrieved chunks.
- [ ] UI shows the answer on the left and retrieved source chunks (title, notebook, Notion link, preview) on the right.
- [ ] App runs end-to-end locally with one command (`uv run app.py`).

### Tech Stack & Constraints

- **Language / Runtime:** Python 3.11+, managed with `uv`.
- **Libraries:**
  - `gradio` — UI
  - `notion-client` — Notion API (DB query + notebook filter; also provides the client passed into `notion-to-md-py`)
  - `notion-to-md-py` — Notion page → Markdown conversion (Python port of Node's `notion-to-md`)
  - `langchain` + `langchain-chroma` — text splitting + vector store integration
  - `chromadb` — local persistent vector DB
  - `openai` — `text-embedding-3-small` embeddings
  - `litellm` — answer LLM (single interface, swap models via env var)
  - `python-frontmatter`, `python-dotenv`
- **Storage:** `data/notion_markdown/*.md`, `chroma_db/`
- **Files:** `ingest.py`, `answer.py`, `app.py`, plus `utils.py` for thin wrappers around `notion-to-md-py` + any post-processing.
- **Budget target:** ≤ $0.50 per full re-index of 50 pages.

### Conversion library notes

**Library:** [`notion-to-md-py`](https://github.com/SwordAndTea/notion-to-md-py) — Python port of `souvikinator/notion-to-md`, MIT, actively maintained (last push 11 May 2026, 4 contributors).

**Smoke test result (this project):** runs cleanly on a sample notes page; cross-page mentions preserved as Markdown links (NOT recursed) — correct behavior for a single-database MVP.

**Expected coverage (from the Node parent's track record + smoke test):**

- Paragraphs, headings, bullets, numbered lists, code (with language), quotes, dividers, to-dos, toggles, callouts — handled.
- Cross-page links / page mentions — kept as Markdown links, no recursion. ✅
- Inline databases (`child_database`) — likely rendered as a link or skipped. Not a problem; we query the DB ourselves via `notion-client`.
- Images — caption / URL only, no binary download (lib limitation, fine for MVP).

**Risks to spot-check BEFORE running the full 20-page sync:**

- **Multi-column layouts** (this Week 5 page is two-column — the right "Notes" column is the most information-dense part). Lib likely flattens left → right or drops a column. Verify on at least one column-heavy page; if the right column disappears, half the indexable content goes with it.
- **Synced blocks** — may render as empty or reference-only. Verify.
- **Deeply nested toggles** — verify children aren't truncated.

**Contingency if a critical gap appears:** add a targeted transform in `utils.post_process_md(md)`, or monkey-patch the lib's per-block renderer. The custom walker design from earlier PRD drafts is the documented fallback if upstream coverage proves unworkable — do NOT build it preemptively.

### Features & TODOs

#### Feature 1 — Notion Notes Sync (P0)

Fetch selected pages from one Notion Notes database and save each as a local Markdown file.

**Acceptance:**

- Clicking the Gradio "Sync Notion" button writes `.md` files into `data/notion_markdown/`.
- Old `.md` files are cleared before each full sync.
- Filename pattern: `{slugified-title}__{page_id_short}.md`.
- Each file starts with YAML frontmatter (`page_id`, `title`, `url`, `last_edited_time`, `notebook`, `source_type`).

**TODOs:**

- [x] `.env`: `NOTION_TOKEN`, `NOTION_NOTES_DATABASE_ID`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY` (optional), `NOTEBOOK_FILTER` (optional), `MAX_NOTES_TO_SYNC` (optional).
- [x] `ingest.query_notion_pages()` — queries DB with optional notebook filter, returns page objects.
- [x] `ingest.extract_page_meta(page)` — returns metadata dict.
- [x] `ingest.clear_markdown_dir()` — deletes contents of `data/notion_markdown/`.
- [x] `ingest.write_markdown_file(meta, body_md)` — writes frontmatter + body to disk.
- [x] Sync summary string: pages exported, skipped, bytes written.

#### Feature 2 — Page-to-Markdown via notion-to-md-py (P0)

Convert each selected Notion page to Markdown using `notion-to-md-py`. Thin wrapper layer in `utils.py`; no custom block walker unless a coverage gap forces one.

**Acceptance:**

- `utils.convert_page_to_md(page_id, n2m)` returns a Markdown string for any page in the selected notebook.
- Paragraphs, headings, bullets, numbered lists, code blocks (with language), quotes, dividers, to-dos, toggles, and callouts render readably.
- Cross-page links preserved as Markdown links (no recursion).
- Conversion of 20 pages completes in under ~60s on a normal connection.
- Failure on a single page (API error, lib crash) is caught and logged — the loop continues with the remaining pages.

**TODOs:**

- [x] `utils.get_n2m_client(notion)` — returns a configured `NotionToMarkdown(notion)` instance (reused across pages within one sync).
- [x] `utils.convert_page_to_md(page_id, n2m)` — calls `n2m.page_to_markdown(page_id)` then `n2m.to_markdown_string(blocks).get('parent')`. Returns Markdown string.
- [x] `utils.post_process_md(md)` — light cleanup: collapse 3+ blank lines to 2, strip trailing whitespace per line. Only add transforms here when a real spot-check reveals an issue.
- [x] In `ingest.py`, wrap each page conversion in `try/except`; collect failures into a list shown in the sync summary (page_id, title, error).
- [x] Spot-check 3 pages BEFORE the full sync: (a) this Week 5 page (multi-column + toggles + code + callouts), (b) a toggle-heavy page, (c) a page with a Notion table or synced block. Diff against hand-written Markdown.
- [x] If columns flatten badly on (a) → decide between: accept (semantic content preserved, layout lost — fine for RAG), monkey-patch the `column_list` renderer, or write a targeted post-processor.

#### Feature 3 — Markdown Loading & Chunking (P0)

Load Markdown files, parse frontmatter, split into chunks.

**Acceptance:**

- Loader reads every `.md` in `data/notion_markdown/`.
- Frontmatter is parsed and attached as metadata to every chunk.
- Each chunk has numeric `chunk_index` (position inside the page).
- Title and notebook are **prepended into the embedded chunk text** so notebook/title terms are searchable.

**TODOs:**

- [x] `ingest.load_markdown_dir()` — returns list of `{meta, body}` dicts.
- [x] `ingest.parse_frontmatter(text)` — via `python-frontmatter`.
- [x] `ingest.chunk_documents(docs)` — `RecursiveCharacterTextSplitter`, `chunk_size=500`, `chunk_overlap=200`.
- [x] Prepend `f"# {title}\n[notebook: {notebook}]\n\n"` to each chunk's embedded text.
- [x] Print totals: pages loaded, chunks created.

#### Feature 4 — ChromaDB Index Rebuild (P0)

Clear and rebuild a single Chroma collection from current chunks.

**Acceptance:**

- Collection name: `notion_notes`.
- Sync clears the collection before re-adding.
- Each chunk embedded with `text-embedding-3-large`.
- Stored metadata: `page_id`, `title`, `url`, `notebook`, `source_path`, `chunk_index`.

**TODOs:**

- [x] `ingest.get_chroma_client()` — `chromadb.PersistentClient(path="chroma_db")`.
- [x] `ingest.reset_collection()` — drop and recreate `notion_notes`.
- [x] Batch-add chunks (batch size 100) to avoid request size limits.
- [x] Return sync summary: page count, chunk count, time elapsed, estimated cost.

#### Feature 5 — Question Answering with Sources (P0)

Retrieve top chunks and call LLM via LiteLLM grounded in those chunks.

**Acceptance:**

- Retrieves top-k chunks from `notion_notes`.
- Prompt instructs the model to answer only from the provided context.
- If context is insufficient, model says "I couldn't find this in your notes."
- Output includes distinct Notion source links when multiple pages contribute.

**TODOs:**

- [x] `answer.get_retriever(top_k=8)` — wraps Chroma as a LangChain retriever.
- [x] `answer.build_prompt(question, chunks)` — system + user prompt with chunk delimiters.
- [x] `answer.answer_question(question)` — `litellm.completion(model=ANSWER_MODEL, ...)`; default `openai/gpt-4o-mini`.
- [x] Returns `(answer_md, sources_md)`.
- [x] Dedupe sources by `page_id` before formatting.

#### Feature 6 — Gradio App UI (P0)

Local UI with sync, ask, answer panel, sources panel.

**Acceptance:**

- `Sync Notion` button + status output.
- Question textbox + "Ask" button.
- Answer Markdown panel on the left.
- Sources Markdown panel on the right (title, notebook, chunk index, Notion link, ~300-char preview).

**TODOs:**

- [x] `app.build_ui()` — `gr.Blocks` with two-column layout.
- [x] Wire `Sync` → `ingest.sync_notion_notes()`.
- [x] Wire `Ask` → `answer.answer_question()`.
- [x] Truncate long chunk previews so the UI stays readable.
- [x] Smoke test: sync → ask 3 real questions → verify Notion links resolve.

#### Feature 7 — Notebook Filter & Sync Cap (P1)

Keep sync small and cheap during iteration.

**Acceptance:**

- `NOTEBOOK_FILTER` limits sync to one notebook value when set.
- `MAX_NOTES_TO_SYNC` caps page count.
- Active filter + cap appear in the sync status output.

#### Feature 8 — Incremental Sync via last_edited_time (P1)

Avoid re-embedding unchanged pages.

**Acceptance:**

- Local `sync_state.json` stores `{page_id: last_edited_time}`.
- Unchanged pages skipped.
- Removed pages deleted from Chroma.

**TODOs:**

- [ ] Load/save `sync_state.json`.
- [ ] Diff current vs previous `last_edited_time` per page.
- [ ] Delete stale chunks from Chroma by `page_id` before re-adding.

#### Feature 9 — Retrieval Debug Panel (P1)

Inspect retrieved chunks to diagnose bad answers.

**Acceptance:**

- Sources panel shows title, notebook, `chunk_index`, Notion link, and preview.
- User can tell whether a bad answer came from bad retrieval or bad generation.

#### Feature 10 — Cross-Database Search (P2, stretch)

Extend beyond Notes into Tasks / Projects / Journal for true personal-knowledge-worker queries (e.g. "what have I learned about Pydantic across my study notes and project tasks?").

**Acceptance:**

- One Chroma collection with `source_type` metadata, or one collection per source DB.
- Single retriever queries across them.
- Sources panel shows which DB each chunk came from.

#### Feature 11 — Advanced Retrieval (P2, stretch)

Query rewriting, query expansion, reranking, semantic chunking aka asking LLM to chunk the documents — only added after the baseline works.

#### Quality of life features

- Remove links from markdown if possible

### Personal Smoke-Test Questions

Used as sanity checks while building, not as a formal eval harness:

1. "What did I learn about Pydantic validators?"
2. "Explain nDCG and how it differs from MRR in my notes."
3. "What's the carpark booking workflow I keep forgetting?"
4. "Summarise the cracks in naive RAG that Day 3 surfaced."
5. "What's my note-taking flow for each lesson?"

### Assumptions / Open Questions

- One Notion Notes database for MVP; cross-DB is P2.
- Single-user, local-only app.
- `notion-to-md-py` coverage validated on 3 representative pages (one of them multi-column) BEFORE scaling to the full 20-page sync. If a critical gap appears (most likely: column layouts), fall back to targeted post-processing in `utils.post_process_md` or, worst case, the custom walker design preserved as the documented contingency.
- OpenAI for embeddings (cheap + good); LiteLLM for the answer LLM so the model can be swapped via env var.
- Old Markdown files cleared on full sync; incremental sync (P1) preserves them.
- Source links open the Notion page; block-level deeplinking is out of scope for MVP.
- Scope warning: 11 features listed for planning, but only the 6 P0 features are required for the weekend MVP.
