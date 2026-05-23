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

- [x] Load/save `sync_state.json`.
- [x] Diff current vs previous `last_edited_time` per page.
- [x] Delete stale chunks from Chroma by `page_id` before re-adding.

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

<aside>
📎

**Reference:** `jsjasee/ai_course_notes` → `Week5/pro_implementation/ingest.py` and `answer.py`. Scope of this section: **semantic chunking + re-ranking only.** Query rewriting / query expansion are tracked but out of scope here.

</aside>

#### 11a — Semantic Chunking (LLM-as-chunker)

**Idea (your mental model, confirmed against `ingest.py`):** instead of `RecursiveCharacterTextSplitter` splitting on character count, hand each document to an LLM and ask it to emit a list of overlapping chunks. Each chunk is a Pydantic object with three fields — `headline`, `summary`, `original_text` — plus metadata attached separately. The **embedded text** is the concatenation `headline + "\n\n" + summary + "\n\n" + original_text`, so the embedding model sees a query-friendly heading + a paraphrased summary in addition to the raw text. This widens vocabulary surface area (more ways for a user's phrasing to hit) without losing the original wording for the answer LLM to use as context.

**Why it should help my Notion corpus specifically:**

- My notes are messy: code blocks, callouts, multi-column layouts, toggles flattened by `notion-to-md-py`. A character-count splitter slices through this without caring about meaning.
- An LLM chunker can keep a code snippet + its surrounding explanation together, and write a `summary` that uses the vocabulary I'd actually search with (e.g. "the classmethod thing" → summary mentions both `@classmethod` and "required for Pydantic validators").
- This directly attacks the **vocabulary leakage** problem from Feature 12: synthetic test questions were inflating scores because chunks echoed source phrasing. A paraphrased `summary` field breaks that mirror.

**Pydantic schema (mirrors `ingest.py`):**

```python
class Chunk(BaseModel):
    headline: str = Field(description="A brief heading for this chunk, typically a few words, that is most likely to be surfaced in a query")
    summary: str = Field(description="A few sentences summarizing the content of this chunk to answer common questions")
    original_text: str = Field(description="The original text of this chunk from the provided document, exactly as is, not changed in any way")

    def as_result(self, document):
        metadata = {"source": document["source"], "type": document["type"], "page_id": document["page_id"], "title": document["title"], "notebook": document["notebook"], "url": document["url"]}
        return Result(
            page_content=self.headline + "\n\n" + self.summary + "\n\n" + self.original_text,
            metadata=metadata,
        )

class Chunks(BaseModel):
    chunks: list[Chunk]
```

**Chunk-count hint in the prompt (the `how_many` trick from `ingest.py`):**

Instead of fixing the chunk count, compute a soft target from doc length and let the LLM deviate as needed:

```python
AVERAGE_CHUNK_SIZE = 100  # tune per corpus; pro_implementation uses 100 for Insurellm md docs
how_many = (len(document["text"]) // AVERAGE_CHUNK_SIZE) + 1
```

Then embed `{how_many}` into the prompt as "probably split into at least N chunks, but use judgment." For my Notion pages (the Week 5 page itself is huge), `AVERAGE_CHUNK_SIZE` will need tuning — start with `100` characters → expect dozens of chunks per long page. **Sanity tune:** run on the Week 5 page first, eyeball chunk granularity, then bump `AVERAGE_CHUNK_SIZE` up if chunks are too small or down if a single chunk is swallowing multiple distinct concepts.

**Prompt (adapted from `make_prompt` in `ingest.py`):**

```python
def make_prompt(document):
    how_many = (len(document["text"]) // AVERAGE_CHUNK_SIZE) + 1
    return f"""
You take a document and split it into overlapping chunks for a personal Notion knowledge base.

The document is from notebook: {document['notebook']}
The document title is: {document['title']}
The document source path is: {document['source']}

A chatbot will use these chunks to answer questions about the user's own study notes, workflows, and learnings.
Divide the document so the ENTIRE document is preserved across chunks — leave nothing out.
This document should probably split into at least {how_many} chunks; deviate if the content asks for it.
Overlap chunks by ~25% (~50 words) so context is preserved at boundaries.

For each chunk: provide a headline (a few words), a summary (1-3 sentences in plain vocabulary the user might actually search with — including abbreviations and synonyms), and the original_text verbatim.

Document:

{document['text']}

Respond with the chunks.
"""
```

**Parallelism (`multiprocessing.Pool` pattern):**

The LLM call is the bottleneck. `pro_implementation/ingest.py` uses `multiprocessing.Pool` with `WORKERS = 3` and `pool.imap_unordered` + `tqdm` for a progress bar. **Tenacity** decorator on `process_document` for exponential backoff on rate-limit errors (`wait_exponential(multiplier=1, min=10, max=240)`).

```python
WORKERS = 3  # drop to 1 if rate-limited
wait = wait_exponential(multiplier=1, min=10, max=240)

@retry(wait=wait)
def process_document(document):
    messages = [{"role": "user", "content": make_prompt(document)}]
    response = completion(model=MODEL, messages=messages, response_format=Chunks)
    doc_as_chunks = Chunks.model_validate_json(response.choices[0].message.content).chunks
    return [chunk.as_result(document) for chunk in doc_as_chunks]

def create_chunks(documents):
    chunks = []
    with Pool(processes=WORKERS) as pool:
        for result in tqdm(pool.imap_unordered(process_document, documents), total=len(documents)):
            chunks.extend(result)
    return chunks
```

**Cost / time budget:** semantic chunking calls the LLM once per document. For 20–50 Notion pages × `gpt-4.1-nano` (or `gpt-4o-mini`) with structured output → still under the ≤ $0.50 re-index target, but each full re-index now takes minutes, not seconds. Combine with **Feature 8 (incremental sync)** so only changed pages get re-chunked.

**Acceptance:**

- [ ] `Chunk(BaseModel)` and `Chunks(BaseModel)` Pydantic classes added to `ingest.py` (sit alongside / replace the current `RecursiveCharacterTextSplitter` path; keep the old path behind a flag for A/B in evals).
- [ ] `make_prompt(document)` produces a prompt with `how_many = (len(text) // AVERAGE_CHUNK_SIZE) + 1`.
- [ ] `process_document` wrapped with `@retry(wait=wait_exponential(...))` (tenacity).
- [ ] `create_chunks` uses `multiprocessing.Pool(WORKERS)` with `imap_unordered` + `tqdm`.
- [ ] Embedded text = `headline + "\n\n" + summary + "\n\n" + original_text`.
- [ ] Metadata still carries `page_id`, `title`, `url`, `notebook`, `source_path`, `chunk_index`.
- [ ] Re-run Feature 12 evals against baseline (recursive char splitter) vs semantic chunking — record per-category deltas (MRR / nDCG / Recall@k / answer accuracy).

**Open questions to resolve while building:**

- What's the right `AVERAGE_CHUNK_SIZE` for my Notion notes? Pro_implementation uses 100 for tidy Insurellm markdown; my notes are denser. Spot-check on the Week 5 page first.
- Does the LLM faithfully return `original_text` verbatim, or does it paraphrase under the hood? Add a hash check: every `original_text` substring should appear in the source doc; flag chunks where it doesn't.

#### 11b — LLM Re-ranking

**Idea (your mental model, confirmed against `answer.py`):** retrieve more chunks than we need from Chroma, then call an LLM to re-rank them by relevance to the original question, keep the top N, and only THOSE go into the final answer prompt. The re-ranker LLM never sees the answer task — it only emits a list of chunk IDs in relevance order.

**Why it should help my eval scores:**

- Embedding similarity is a single shot; it can rank a topically-close-but-irrelevant chunk above a precise hit. The re-ranker reads the question + chunks together and can spot the actual fit.
- Directly improves nDCG (distribution-of-relevance metric) more than MRR.
- For `multi_doc` questions (Feature 12 category), re-ranking biases the top-K toward chunks from _different_ pages, helping synthesis.
- Composes naturally with query expansion: retrieve from both original + rewritten query, dedupe, re-rank the union, keep top-K. (Pro_implementation already does this in `fetch_context`; I'm tracking query expansion separately but the merge-then-rerank pattern stays.)

**Constants (from `answer.py`):**

```python
RETRIEVAL_K = 20  # fetch 20 from Chroma
FINAL_K = 10     # keep top 10 after re-ranking
```

**Pydantic schema for the re-ranker's output:**

```python
class RankOrder(BaseModel):
    order: list[int] = Field(
        description="The order of relevance of chunks, from most relevant to least relevant, by chunk id number"
    )
```

The LLM returns ONLY a list of integers (the chunk IDs we showed it). Structured output via `response_format=RankOrder` makes this bullet-proof against prose drift.

**Re-ranker function (lifted + adapted from `answer.py`):**

```python
@retry(wait=wait)
def rerank(question, chunks):
    system_prompt = """
You are a document re-ranker.
You are provided with a question and a list of relevant chunks of text from a query of a knowledge base.
The chunks are provided in the order they were retrieved; this is approximately ordered by relevance, but you may be able to improve on that.
You must rank order the provided chunks by relevance to the question, with the most relevant chunk first.
Reply only with the list of ranked chunk ids, nothing else. Include all the chunk ids you are provided with, reranked.
"""
    user_prompt = f"The user has asked the following question:\n\n{question}\n\nOrder all the chunks of text by relevance to the question, from most relevant to least relevant. Include all the chunk ids you are provided with, reranked.\n\nHere are the chunks:\n\n"
    for index, chunk in enumerate(chunks):
        user_prompt += f"# CHUNK ID: {index + 1}:\n\n{chunk.page_content}\n\n"
    user_prompt += "Reply only with the list of ranked chunk ids, nothing else."
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    response = completion(model=MODEL, messages=messages, response_format=RankOrder)
    order = RankOrder.model_validate_json(response.choices[0].message.content).order
    return [chunks[i - 1] for i in order]  # chunk ids are 1-indexed in the prompt
```

**Wiring into `fetch_context` (the "two places" you mentioned):**

In `pro_implementation/answer.py`, re-rank is called inside `fetch_context` AFTER retrieval and BEFORE the answer LLM sees anything. The same `rerank()` call serves both purposes — it's just called once, and its output flows into the answer prompt.

```python
def fetch_context(original_question):
    # 1. Retrieve RETRIEVAL_K=20 chunks (optionally union with query-expansion results)
    chunks = fetch_context_unranked(original_question)
    # 2. Re-rank with LLM
    reranked = rerank(original_question, chunks)
    # 3. Keep top FINAL_K=10
    return reranked[:FINAL_K]

def answer_question(question, history=[]):
    chunks = fetch_context(question)  # already re-ranked + trimmed
    messages = make_rag_messages(question, history, chunks)
    response = completion(model=MODEL, messages=messages)
    return response.choices[0].message.content, chunks
```

**Gotchas / footguns to watch:**

- **1-indexed vs 0-indexed.** The prompt uses `CHUNK ID: {index + 1}` (1-indexed), so the return path uses `chunks[i - 1]`. If the LLM ever returns a 0 or skips a number, the indexing breaks silently. Defensive code: validate `order` is a permutation of `1..len(chunks)` before slicing; if not, fall back to the unranked order and log it.
- **Chunk size in the prompt.** Stuffing 20 chunks × `headline+summary+original_text` into the user prompt can blow the context window on long documents. With semantic chunking active, the embedded text is bigger than a raw character-split chunk. If context overflow becomes a problem, send only `headline + summary` to the re-ranker (NOT `original_text`) — same ranking quality at a fraction of the tokens.
- **Cost.** Re-rank adds ONE LLM call per user query. Use a cheap model (`gpt-4.1-nano` / `gpt-4o-mini`) for re-ranking; reserve the stronger model for the actual answer.
- **Latency.** Re-ranking adds ~1-2s per query. For evals (Feature 12), this means the 100-question eval takes longer; parallelize the eval loop.

**Acceptance:**

- [ ] `RankOrder(BaseModel)` Pydantic class in `answer.py`.
- [ ] `rerank(question, chunks)` function with `@retry(wait=wait_exponential(...))`.
- [ ] `fetch_context` retrieves `RETRIEVAL_K=20` from Chroma, calls `rerank`, returns `reranked[:FINAL_K]`.
- [ ] `FINAL_K` exposed as a config so I can A/B 5 vs 10 vs 15 in evals.
- [ ] Defensive validation: if `order` isn't a clean permutation of `1..N`, fall back to unranked + log a warning.
- [ ] Re-run Feature 12 evals: baseline (no re-rank) vs re-rank. Track nDCG and answer-LLM-judge deltas per category — `multi_doc` and `specific_fact` should benefit most.

**Open questions to resolve while building:**

- Does sending only `headline + summary` to the re-ranker (omitting `original_text`) match the quality of sending the full embedded text? Cheap experiment, big context-window savings.
- Which model for re-ranking? `gpt-4.1-nano` vs `gpt-4o-mini` vs an open-source judge via OpenRouter — measure rank-correlation against a hand-ranked gold set for 5 representative queries.

#### Recommended build order

1. Get **11b (re-ranking)** working FIRST against the existing baseline (RecursiveCharacterTextSplitter chunks). It's the smaller change, isolates one variable, and gives a clean eval delta.
2. Then layer **11a (semantic chunking)** on top. Re-run evals with both on/off in a 2x2 matrix (baseline / +rerank / +semantic / +both) so I can attribute the gains correctly instead of one big mush of changes.
3. Only after that, revisit query rewriting / query expansion (separate ticket, out of scope for this Feature 11 elaboration).

#### Feature 12 — Evals (P1)

A 100-question evaluation harness (jsonl test set + forked evaluator) used to compare chunking strategies, embedding models, prompts, and retrieval techniques with quantitative feedback rather than vibes. Forked from `Week5/pro_implementation/eval.py` with deliberate modifications for personal-notes domain (not Insurellm-style factoid retrieval).

Path to this week 5 folder: /Users/tayjiasheng/AI Projects/Notes/Week5

**Design principles (locked in via Mode 9 sparring session, 20 May 2026):**

- **Keywords grade retrieval, not answers.** Keywords are matched against retrieved chunks (`doc.page_content`), NOT the generated answer. Answer quality is graded separately via LLM-as-judge.
- **Per-category metrics, not one averaged number.** Question shapes need different primary metrics — averaging across shapes hides signal.
- **Vocabulary leakage is real.** LLM-generated questions inherit document phrasing → inflated retrieval scores. Mitigated by mixing hand-written questions with LLM-generated ones, and forcing the generator to rephrase using different vocabulary (abbreviations, slang, vague phrasing) instead of echoing the notes.
- **Negative tests are non-negotiable.** Without questions whose correct answer is _"not in my notes,"_ hallucination is invisible.

**Test set composition (`tests.jsonl`, 50 questions):**

- 15 (30%) — hand-written from real usage / seed questions across all 4 shapes
- 25 (50%) — LLM-generated, seeded with the 15 hand-written, vetted manually
- 10 (20%) — negative cases (topics genuinely absent from notes)

**Question shape taxonomy** — every question tagged with `category`:

| Shape           | Example                                            | Primary metric(s)                       |
| --------------- | -------------------------------------------------- | --------------------------------------- |
| `existence`     | "Have I covered X before?"                         | Recall@k + LLM-judge (completeness)     |
| `multi_doc`     | "What are my notes on X?"                          | Recall@k + nDCG + LLM-judge (synthesis) |
| `specific_fact` | "Who do I contact for X?" / "What do I get for Y?" | MRR + LLM-judge (accuracy)              |
| `negative`      | Topics genuinely not in notes                      | Refusal correctness (binary)            |

**jsonl schema (per line):**

- `question` (string)
- `category` (enum: `existence` | `multi_doc` | `specific_fact` | `negative`)
- `keywords` (list[str]) — expected to appear in retrieved chunks; for `negative` cases this is `[]`
- `reference_answer` (string) — for `negative` cases: _"I couldn't find this in your notes."_
- `expected_source_ids` (optional list[str]) — page IDs that _should_ surface in retrieval, most useful for `multi_doc`

**Synthetic generation vetting heuristic:**

- Seed the generator with the 15 hand-written questions as few-shot examples
- Prompt it to deliberately vary vocabulary: ~1 in 3 should use abbreviations, colloquialisms, or vague phrasing
- For each batch of 25, manually replace any question whose phrasing is >70% identical to a sentence in the source doc
- Heuristic: if it reads like a textbook, kill it; if it reads like something you'd type at 11pm tired, ship it

**Acceptance:**

- `tests.jsonl` contains 100 questions, each validated by a Pydantic `TestQuestion` schema (extends pro_implementation's with `expected_source_ids` and the 4-value `category` enum).
- `eval.py` (forked) reports MRR, nDCG, Recall@k, keyword coverage **per category** AND overall.
- `RefusalEval` (new) grades `negative` questions on whether the bot correctly said it couldn't find the info — binary score.
- `AnswerEval` (modified) weights _completeness_ heavily for `multi_doc`, _accuracy_ heavily for `specific_fact`.
- Running evals against the current baseline produces per-category dashboards; changing `chunk_size` in `ingest.py` and re-running shows whether the change helped, hurt, or was neutral _per shape_.
- Eval run completes in under ~5 min for all 100 questions (parallelized where possible).

**TODOs:**

- [x] Write 15 seed questions by hand across all 4 shapes (3-4 per shape, drawn from real usage of the bot + the 5 personal smoke-test questions above). Non-negotiable — these are the foundation.
- [x] Draft prompt for synthetic question generator (handoff to Mode 5 Transformer #12).
- [x] Run generator with seeds; vet 25 outputs against the heuristic above.
- [x] Hand-curate 10 negative cases (topics I'm certain my notes don't cover).
- [x] Define Pydantic `TestQuestion` schema with `category` enum + optional `expected_source_ids`.
- [x] Fork `Week5/pro_implementation/eval.py` into project's `evaluation/eval.py`.
- [x] Add `calculate_recall_at_k(keywords, retrieved_docs, k)` — binary, did ANY relevant chunk appear in top k.
- [x] Add per-category aggregation: group by `category`, report metrics per group AND overall.
- [x] Add `RefusalEval(BaseModel)` Pydantic class + LLM-judge call for `negative` questions.
- [x] Modify `AnswerEval` prompt to apply category-aware weighting.
- [x] Wire eval results into Gradio UI (or CLI table) with per-category breakdown. (This one would be `evaluator.py` with a separate Gradio UI interface
- [x] Run baseline eval; record scores per category as the reference point before any RAG-technique experiments.

#### Feature 13 — Parallelized Evals + Dashboard UI Polish (P1)

Run the 100-question eval set in parallel via `multiprocessing.Pool` with a tunable `WORKERS` constant, surface per-category bar charts in `evaluator.py`, color-code the headline numbers so I can tell at a glance whether changes are helping or hurting, and add `tqdm` progress bars in BOTH the CLI and the Gradio UI for visual feedback during long runs.

<aside>
📎

**Reference:** [`Week5/evaluator.py`](https://github.com/jsjasee/ai_course_notes/blob/main/Week5/evaluator.py) in `jsjasee/ai_course_notes` — same color-coded HTML metric cards + `gr.BarPlot` per category pattern. The file already exists in this project's root folder; Feature 13 modifies it in place rather than creating a new one.

</aside>

**Design decisions (locked via clarifying questions, 23 May 2026):**

- **Parallelism:** `multiprocessing.Pool` for consistency with Feature 11a's semantic-chunking pattern. Caveat: LLM eval calls are I/O-bound, so `ThreadPoolExecutor` would be the textbook choice — but `mp.Pool` works fine here and keeps the codebase uniform. If process startup overhead becomes a problem (each test is fast), the swap to `concurrent.futures.ThreadPoolExecutor` is a 5-line change.
- **`WORKERS` is a top-of-file constant** — start at 5, drop if rate-limited.
- **Color thresholds are top-of-file constants** — calibrated lower than the Insurellm sample because the personal-notes domain will have a weaker baseline. Tune up as the baseline improves.
- **Charts:** MRR, nDCG, Recall@k (retrieval) + Accuracy, Completeness (answer), all per-category.
- **tqdm in BOTH places:** CLI (terminal) via `tqdm(pool.imap_unordered(...))` AND Gradio via `gr.Progress()`. They don't fight — tqdm writes to stderr, Gradio writes to the browser.

**Top-of-file constants block (paste at top of `evaluator.py`):**

```python
WORKERS = 5  # drop to 3 if rate-limited

# Retrieval thresholds (tune as baseline improves)
MRR_GREEN, MRR_AMBER = 0.7, 0.5
NDCG_GREEN, NDCG_AMBER = 0.7, 0.5
RECALL_GREEN, RECALL_AMBER = 80.0, 60.0      # percent
COVERAGE_GREEN, COVERAGE_AMBER = 80.0, 60.0  # percent

# Answer thresholds (1-5 scale)
ANSWER_GREEN, ANSWER_AMBER = 4.0, 3.0
```

**Parallel eval runner pattern (mirrors Feature 11a's `create_chunks`):**

```python
from multiprocessing import Pool
from tqdm import tqdm
from tenacity import retry, wait_exponential

wait = wait_exponential(multiplier=1, min=10, max=240)

@retry(wait=wait)
def evaluate_one_retrieval(test):
    return test, evaluate_retrieval(test)

def evaluate_all_retrieval_parallel(progress=None):
    tests = load_tests()
    total = len(tests)
    results = []
    with Pool(processes=WORKERS) as pool:
        for i, (test, result) in enumerate(
            tqdm(
                pool.imap_unordered(evaluate_one_retrieval, tests),
                total=total,
                desc="Retrieval evals",
            ),
            start=1,
        ):
            results.append((test, result))
            if progress is not None:
                progress(i / total, desc=f"Evaluating test {i}/{total}...")
    return results
```

**Extend `get_color` for new metric types:**

```python
elif metric_type == "recall":
    return "green" if value >= RECALL_GREEN else "orange" if value >= RECALL_AMBER else "red"
elif metric_type == "completeness":
    return "green" if value >= ANSWER_GREEN else "orange" if value >= ANSWER_AMBER else "red"
```

**Per-category aggregation (the part the sample only does for one metric):**

After the pool closes, group results by `test.category`. Build ONE `pandas.DataFrame` per metric with columns `Category | <metric>` and feed each to a separate `gr.BarPlot`. Five charts total: 3 retrieval (MRR, nDCG, Recall@k) + 2 answer (Accuracy, Completeness). Use `gr.Row()` to pair them with their matching color-coded metric card on the left.

**Acceptance:**

- [ ] `WORKERS` constant lives at the top of `evaluator.py`; changing it changes parallelism with zero other edits.
- [ ] Eval run for 100 tests completes in roughly `total_time / WORKERS` seconds (with rate-limit headroom).
- [ ] 5 color-coded HTML metric cards visible: MRR, nDCG, Recall@k, Accuracy, Completeness — all using the sample's card pattern but driven by tunable threshold constants.
- [ ] 5 per-category `gr.BarPlot` panels, one per metric, with appropriate `y_lim`.
- [ ] tqdm bar visible in the terminal AND Gradio progress bar updates in the UI during a run.
- [ ] Color thresholds editable from the top of the file without touching layout code.
- [ ] Running the same eval with `WORKERS=1` vs `WORKERS=5` produces identical numbers to 4 decimal places (aggregation must be order-independent).

**TODOs:**

- [ ] Add `WORKERS` + threshold constants block at the top of `evaluator.py`.
- [ ] Wrap each `evaluate_one_*` worker function with `@retry(wait=wait_exponential(...))` from tenacity for rate-limit safety.
- [ ] Replace the existing serial generators (`evaluate_all_retrieval`, `evaluate_all_answers`) with `Pool(processes=WORKERS) + pool.imap_unordered + tqdm(total=...)`.
- [ ] Inside the same loop, call `progress(i/total, desc=...)` to drive the Gradio bar.
- [ ] Extend `get_color` with `recall` and `completeness` branches.
- [ ] Compute per-category aggregates after the pool closes; build 5 DataFrames.
- [ ] Add 3 retrieval `gr.BarPlot` panels (MRR `y_lim=[0,1]`, nDCG `y_lim=[0,1]`, Recall@k `y_lim=[0,100]`) and 2 answer `gr.BarPlot` panels (Accuracy `y_lim=[1,5]`, Completeness `y_lim=[1,5]`).
- [ ] Sanity check: run eval with `WORKERS=1` vs `WORKERS=5` — final per-category numbers must match exactly.
- [ ] Optionally combine retrieval + answer into a single pool pass (one `fetch_context` per test, reused for both) — saves ~50% of retrieval calls. Track as a follow-up if speed matters more than code clarity.

**Gotchas:**

- **`mp.Pool` + LiteLLM + macOS:** child processes don't inherit env vars cleanly under spawn. Call `load_dotenv(override=True)` at module top so each worker re-reads `.env` on import.
- **`imap_unordered` returns out of order:** never rely on result order for aggregation; always read `test.category` off the returned tuple.
- **tqdm + Gradio coexistence:** they don't conflict — tqdm writes to stderr, Gradio writes to the browser. If you see buffering issues in the terminal, force-flush with `tqdm(..., file=sys.stderr, mininterval=0.1)`.
- **Process pickling:** anything passed to `pool.imap_unordered` must be picklable. Pydantic `BaseModel` instances pickle fine; closures and lambdas don't.
- **Rate limits:** if `gpt-4.1-nano` returns 429s at `WORKERS=5`, drop to 3 and bump `wait_exponential(max=240)` higher. Tenacity will absorb the retries silently.

**Open questions:**

- Combined retrieval + answer pool (one `fetch_context` call per test) vs two separate pools — measure once Feature 11a is in.
- Whether to also chart per-category counts (e.g. "how many `multi_doc` tests are there") alongside the metric bars — small UX win, decide after first real run.

#### Quality of life features

- Remove links from markdown if possible
- Change prompts for Notion RAG chatbot
- Move to pydantic instead of formatter

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
