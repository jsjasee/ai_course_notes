# Insurellm RAG Upgrade — improve local RAG retrieval

## Overview
A local RAG project for answering questions about the fictional Insurellm knowledge base.
Use it to test chunk retrieval, document summaries, global indexes, and evaluation tools.

## Features
- Ask questions in a Gradio chat UI.
- Retrieve chunks from Chroma collections.
- Route broad questions through holistic retrieval.
- Generate document summaries and global indexes.
- Extract employee records into JSONL.
- Evaluate retrieval and answer quality.

## Installation
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install gradio python-dotenv pandas pydantic chromadb openai litellm tenacity tqdm
```

## Usage
Run the chat app.

```bash
python app.py
```

Run the evaluation dashboard.

```bash
python evaluator.py
```

Run one evaluation test.

```bash
python evaluation/eval.py 0
```

Generate employee records.

```bash
python pro_implementation/ingest.py
```

## Configuration
| Name | Default | What it does |
| --- | --- | --- |
| `OPENAI_API_KEY` | none | Authenticates OpenAI embeddings and models. |
| `OPENROUTER_API_KEY` | none | Authenticates OpenRouter answer models. |
| `knowledge-base/` | required | Stores source markdown files. |
| `preprocessed_db/` | auto-created | Stores persisted Chroma collections. |
| `structured/employees.jsonl` | generated | Stores extracted employee records. |
| `text-embedding-3-large` | set in code | Embeds documents for vector search. |
