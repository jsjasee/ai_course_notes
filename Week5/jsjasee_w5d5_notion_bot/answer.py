import os

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from litellm import completion
from pydantic import BaseModel, Field

from ingest import CHROMA_DIR, COLLECTION_NAME, EMBEDDING_MODEL

ANSWER_MODEL = os.getenv("ANSWER_MODEL", "openrouter/openai/gpt-oss-120b")
QUERY_REWRITE_MODEL = os.getenv("QUERY_REWRITE_MODEL", "openai/gpt-4.1-nano")
RERANK_MODEL = os.getenv("RERANK_MODEL", "openai/gpt-4.1-nano")
RETRIEVAL_K = int(os.getenv("RETRIEVAL_K", "20"))
FINAL_K = int(os.getenv("FINAL_K", "10"))


class RankOrder(BaseModel):
    """Structured reranker output listing chunk ids by descending relevance."""

    order: list[int] = Field(
        description="Chunk ids ordered from most relevant to least relevant."
    )


def get_retriever(top_k=20):
    """Build a retriever over the local `notion_notes` Chroma collection.

    Args:
        top_k: Number of chunks to retrieve per question.

    Returns:
        LangChain retriever configured for similarity search.
    """
    vectorstore = Chroma(
        persist_directory=str(CHROMA_DIR),
        collection_name=COLLECTION_NAME,
        embedding_function=OpenAIEmbeddings(model=EMBEDDING_MODEL),
    )
    return vectorstore.as_retriever(search_kwargs={"k": top_k})


def build_prompt(question, chunks):
    """Create the grounded prompt sent to the answer model.

    Args:
        question: User question string.
        chunks: Retrieved chunk documents.

    Returns:
        LiteLLM messages list with system and user turns.
    """
    context = "\n\n".join(
        f"<chunk {i}>\n{chunk.page_content}\n</chunk {i}>"
        for i, chunk in enumerate(chunks, start=1)
    )
    return [
        {
            "role": "system",
            "content": "Answer only from the provided notes context. "
            "Act like a learning assistant: explain clearly, teach the idea step by step when useful, and prefer the wording and concepts already present in the notes. "
            "If the notes support only part of the answer, say what is supported and what is missing. "
            "If the context is insufficient, say: I couldn't find this in your notes.",
        },
        {
            "role": "user",
            "content": f"Question:\n{question}\n\nContext:\n{context}",
        },
    ]


# Feature 5.5: history-aware retrieval
def _recent_user_questions(history, limit=5):
    """Return up to the last `limit` user questions from chat history."""
    if not history:
        return []
    questions = [turn["content"] for turn in history if turn.get("role") == "user"]
    return questions[-limit:]


# Feature 5.5: history-aware retrieval
def rewrite_question(question, history=None):
    """Rewrite the latest question into a standalone retrieval query."""
    prior_questions = _recent_user_questions(history)
    if not prior_questions:
        # if this question is the FIRST question, don't rewrite
        return question

    history_block = "\n".join(f"- {item}" for item in prior_questions)
    response = completion(
        model=os.getenv("QUERY_REWRITE_MODEL", QUERY_REWRITE_MODEL),
        messages=[
            {
                "role": "system",
                "content": (
                    "You are in conversation with a user, answering questions regarding their notes."
                    "Rewrite the latest user question into one standalone retrieval query, THAT IS most likely to surface content. "
                    "Prioritize the latest question. Use earlier user questions only when they clarify references or scope. "
                    "Drop irrelevant history. IMPORTANT: Return ONLY the rewritten query."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Previous user questions:\n{history_block}\n\n"
                    f"Latest user question:\n{question}"
                ),
            },
        ],
    )
    return response.choices[0].message.content.strip() or question


def rerank(question, chunks):
    """Return retrieved chunks reordered by LLM-judged relevance.

    Args:
        question: Original user question.
        chunks: Retrieved chunk documents in approximate relevance order.

    Returns:
        The same chunk list, reordered from most relevant to least relevant.
    """
    if len(chunks) < 2:
        return chunks

    chunk_block = "\n\n".join(
        f"# CHUNK ID: {index}\n\n{chunk.page_content}"
        for index, chunk in enumerate(chunks, start=1)
    )  # we are given each chunk an id based on its position in the list
    response = completion(
        model=os.getenv("RERANK_MODEL", RERANK_MODEL),
        messages=[
            {
                "role": "system",
                "content": (
                    "You rerank retrieved note chunks for question answering. "
                    "Return every provided chunk id exactly once, ordered from most relevant to least relevant."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Question:\n{question}\n\n"
                    "Rerank all chunk ids by relevance to the question.\n\n"
                    f"Chunks:\n\n{chunk_block}"
                ),
            },
        ],
        response_format=RankOrder,  # so its just a list of numbers (chunk ids) that is being returned
    )
    ranked_ids = RankOrder.model_validate_json(
        response.choices[0].message.content
    ).order
    ranked_chunks = [
        chunks[chunk_id - 1] for chunk_id in ranked_ids if 1 <= chunk_id <= len(chunks)
    ]
    return ranked_chunks if len(ranked_chunks) == len(chunks) else chunks


def answer_question(question, history=None, top_k=None):
    """Answer a question from the indexed notes and format distinct sources.

    Args:
        question: User question string.
        history: Optional chat history for Feature 5.5 query rewriting.
        top_k: Optional number of reranked chunks kept for the answer prompt.

    Returns:
        Tuple of `(answer_md, sources_md)`.
    """
    load_dotenv()
    final_k = max(1, top_k or FINAL_K)
    retrieval_k = max(RETRIEVAL_K, final_k)
    retrieval_query = rewrite_question(question, history=history)
    print(retrieval_query)
    retrieved_chunks = get_retriever(top_k=retrieval_k).invoke(retrieval_query)
    if not retrieved_chunks:
        return "I couldn't find this in your notes.", "No sources found."
    chunks = rerank(question, retrieved_chunks)[
        :final_k
    ]  # get the first K chunks from the reranked chunks

    response = completion(
        model=os.getenv("ANSWER_MODEL", ANSWER_MODEL),
        messages=build_prompt(question, chunks),
    )
    answer_md = response.choices[0].message.content.strip()

    # De-duplicating the repeated chunks by page_id if any (dedupe only affects what user sees in the gradio app, NOT what the LLM sees.)
    seen_page_ids = set()
    source_lines = []
    for chunk in chunks:
        meta = chunk.metadata
        page_id = meta["page_id"]
        # if page_id in seen_page_ids:
        #     continue
        seen_page_ids.add(page_id)
        preview = chunk.page_content.replace("\n", " ").strip()[:300]
        source_lines.append(
            f"- **{meta['title']}** ({meta.get('notebook', '')}) "
            f"[Notion link]({meta['url']})\n"
            f"  chunk {meta['chunk_index']}: {preview}..."
        )

    return answer_md, "\n".join(source_lines)
