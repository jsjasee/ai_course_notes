# Insurellm RAG Upgrade

## What it is

A small upgrade to the Week 5 Insurellm RAG pipeline for a course assignment. The goal is to fix two weak spots: holistic questions that need many documents, and structured questions that need counting or averaging over employee data.

MAKE SURE TO ADD THE KNOWLEDGE BASE FILES FROM ED DONNER FIRST!

## Success Criteria

- [ ] Direct fact questions still work and do not noticeably regress in existing evals.
- [ ] Holistic questions like “Who are all the winners of the IIOTY award across all years?” retrieve broad context from summaries/indexes instead of only one entity.
- [ ] Structured questions like “How many employees have a current salary under $80,000?” return a computed number instead of an LLM guess.
- [ ] Structured questions like “What is the average tenure of employees in the engineering department?” return a computed average using the employee table.
- [ ] Eval results improve for `holistic/spanning`, `numerical`, and structured-style questions, especially keyword coverage and LLM-judge accuracy.

## Tech Stack & Constraints

- Language / Runtime: Python
- Framework / Libraries: Chroma, LiteLLM, Pydantic, OpenAI SDK, Tenacity
- Storage / Data: Chroma collections for chunks/summaries/indexes; JSONL sidecar file for structured employee records
- Deployment: Local notebook / local Python scripts only
- Constraints: Buildable within 3 hours; keep the current Chroma setup; do not replace the vector database; do not use a bigger answer model as the main fix; use simple rule-based query routing first; new files are allowed if they keep the implementation clearer

## Features & TODOs

### Feature 1 — Document Summary Collection

Priority: P0
Description: Create one document-level summary per source markdown file. This gives the RAG system a “bird’s-eye view” before it fetches detailed chunks.

Acceptance Criteria:

- Each source markdown document produces one summary record.
- Each summary record includes the source path, document type, short summary, and key facts.
- Summaries are embedded and stored in a separate Chroma collection called `doc_summaries`.

TODOs:

- [✅] In `ingest.py`, create a `DocumentSummary` Pydantic model with fields: `title`, `entity_name`, `summary`, `key_facts`, and `topics`.
- [✅] In `ingest.py`, create a `summarize_document(document)` function that sends one full markdown document to the LLM and returns one `Result`.
- [✅] Add metadata to each summary result: `source`, `doc_id`, `type`, `level="doc_summary"`, and `entity_name`.
- [✅] Update `create_embeddings()` so it accepts a `collection_name` argument instead of always writing to `"docs"`.
- [✅] In the ingestion flow, call `summarize_document()` for every document and save the results into the `doc_summaries` Chroma collection.
- [✅] Run ingestion and confirm Chroma contains both `docs` and `doc_summaries`.

### Feature 2 — Global Index Documents (the cheat sheet part, aka hierarchical RAG)

Priority: P0
Description: Create a few small cross-document index docs for questions that ask about “all” or “every” item. These indexes help the system retrieve complete lists instead of one matching example. For holistic questions, we would search the global index docs -> document summaries -> normal chunks from selected source docs

Acceptance Criteria:

- A `products_index` exists and lists every Insurellm product with key facts.
- An `employee_index` exists and lists roles, departments, salaries, and achievements.
- Index docs are embedded and stored in a separate Chroma collection called `global_indexes`.

TODOs:

- [✅] In `ingest.py`, create a `GlobalIndexDoc` Pydantic model with fields: `index_type`, `title`, `summary`, and `facts`.
- [✅] Create a `make_global_index_docs(document_summaries)` function that asks the LLM to generate `products_index` and `contracts_index` and `employee_index` from the document summaries.
- [✅] Format each global index doc as readable text with bullet points before embedding.
- [✅] Add metadata to each global index result: `level="global_index"` and `index_type`.
- [✅] Save the global index docs into a Chroma collection called `global_indexes`.
- [✅] Manually inspect the generated `awards_index` and `products_index` once to check that key names and facts are present.

### Feature 3 — Holistic Question Retrieval Path

Priority: P0
Description: Add a separate retrieval path for holistic questions. Instead of searching only chunk vectors, the system first searches global indexes and document summaries, then fetches supporting chunks.

Acceptance Criteria:

- Questions containing phrases like “all”, “every”, “list all”, “who are all”, or “across all” use the holistic retrieval path.
- Holistic retrieval searches `global_indexes` and `doc_summaries` before fetching child chunks from `docs`.
- Final context includes both overview records and detailed source chunks.

TODOs:

- [✅] In `answer.py`, create an `is_holistic_question(question)` function using simple lowercase keyword rules.
- [✅] In `answer.py`, load three Chroma collections: `docs`, `doc_summaries`, and `global_indexes`.
- [✅] Create `query_collection(collection, question, n_results)` that embeds the question and returns a list of `Result` objects.
- [✅] Create `fetch_chunks_for_sources(sources, max_chunks_per_source)` that gets child chunks from the `docs` collection by `source`.
- [✅] Create `fetch_holistic_context(question)` that retrieves top global indexes, top document summaries, selects unique source files, and fetches supporting chunks.
- [✅] Update `fetch_context(question)` so holistic questions use `fetch_holistic_context(question)` and normal questions keep the existing query expansion + reranking path.
- [✅] Test manually with: “Who are all the winners of the Insurellm Innovator of the Year award across all years?”

### Feature 4 — Employee Structured Records

Priority: P0
Description: Convert employee markdown profiles into a simple `employees.jsonl` table. This lets Python compute salary counts and tenure averages instead of asking the LLM to guess from chunks.

Acceptance Criteria:

- A file exists at `structured/employees.jsonl`.
- Each employee row includes name, department, current salary, start date, job title, location, and source.
- Salary is stored as an integer number of dollars.
- Start date is stored in a consistent parseable format where possible.

TODOs:

- [✅] Create a `structured/` folder under the Week 5 project folder.
- [✅] In `ingest.py`, create an `EmployeeRecord` Pydantic model with fields: `name`, `department`, `current_salary`, `start_date`, `job_title`, `location`, `education` and `source`.
- [✅] Create `extract_employee_record(document)` that only runs on employee/profile documents and returns one `EmployeeRecord`.
- [✅] Make the extraction prompt explicitly say: “Do not infer missing values. Use null if the field is not present.”
- [✅] Create `write_employee_records(documents)` that writes one JSON object per employee into `structured/employees.jsonl`.
- [✅] Run the employee extraction and manually inspect at least 3 rows for correct salary and start date values.

### Feature 5 — Structured Question Answering Path (not implemented - marginal gains)

Priority: P0
Description: Add a rule-based route for questions that require counting, filtering, or averaging. Python reads `employees.jsonl`, computes the answer, and returns a short evidence context.

Acceptance Criteria:

- Salary-under-threshold questions return an exact computed count.
- Average-tenure-by-department questions return an exact computed average.
- The LLM does not perform the arithmetic itself.
- The returned context includes the matching employee names or records used in the calculation.

TODOs:

- [ ] In `answer.py`, create `is_structured_question(question)` using rules for phrases like `how many employees`, `salary under`, `salary over`, `average tenure`, and `department`.
- [ ] Create `load_employee_records()` that reads `structured/employees.jsonl` and returns a list of dictionaries.
- [ ] Create `count_employees_salary_below(max_salary)` that filters employees by `current_salary < max_salary` and returns the count plus evidence.
- [ ] Create `average_tenure_by_department(department, as_of_date)` that filters employees by department and computes average tenure in years.
- [ ] Set a fixed `AS_OF_DATE` constant so eval results stay stable.
- [ ] Create `answer_structured_question(question)` that parses the salary threshold or department from the question and calls the correct Python function.
- [ ] Update `answer_question(question, history=[])` so structured questions use `answer_structured_question(question)` before normal RAG retrieval.
- [ ] Test manually with: “How many employees at Insurellm have a current salary under $80,000?”
- [ ] Test manually with: “What is the average tenure of employees in the engineering department?”

### Feature 6 — Evaluation Checks

Priority: P1
Description: Add a small evaluation pass to confirm the upgrade improves the intended failure modes without breaking direct facts.

Acceptance Criteria:

- At least one holistic test improves in keyword coverage or answer completeness.
- At least two structured tests return exact computed answers.
- Existing direct-fact questions still return correct answers in spot checks.

TODOs:

- [ ] Add or identify test questions for IIOTY winners, product summaries, salary count, and average tenure.
- [ ] Run the current eval script before changes and save the baseline scores in a local note.
- [ ] Run the eval script after changes and compare keyword coverage, nDCG, MRR, and LLM-judge scores.
- [ ] Confirm at least 3 direct-fact questions still answer correctly.
- [ ] Add a short comment in the notebook explaining which metrics improved and why.

## Assumptions / Open Questions

- Assumption: The main implementation files are `Week5/pro_implementation/ingest.py` and `Week5/pro_implementation/answer.py`.
- Assumption: The answer model remains the current LiteLLM model instead of upgrading to a larger model.
- Assumption: The embedding model remains OpenAI `text-embedding-3-large`.
- Assumption: JSONL is better than SQLite for this 3-hour MVP because it is easier to create, inspect, and debug as a beginner.
- Assumption: The LLM may extract employee records during ingestion, but Python must do the final counting and averaging.
- Assumption: Rule-based routing is enough for the MVP and avoids adding another LLM call before every question.
- Assumption: `document["source"]` can be reused as `doc_id` because each markdown file is already a stable parent document.
- Open Question: The exact folder name for employee documents may need checking before writing `extract_employee_record(document)`.
- Open Question: The fixed `AS_OF_DATE` for tenure calculations should match the dataset’s intended “current” date if one exists.
- Open Question: The global indexes should be manually inspected because LLM-generated indexes can omit rare facts.
