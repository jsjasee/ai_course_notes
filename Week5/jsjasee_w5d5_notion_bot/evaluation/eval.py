import math
import os
from collections import defaultdict

from dotenv import load_dotenv
from litellm import completion
from pydantic import BaseModel, Field

from answer import ANSWER_MODEL, build_prompt, get_retriever
from evaluation.test import QuestionCategory, TestQuestion, load_tests

load_dotenv(override=True)
JUDGE_MODEL = os.getenv("EVAL_JUDGE_MODEL", "openai/gpt-4.1-nano")


class RetrievalEval(BaseModel):
    """Retrieval metrics computed from retrieved chunk text."""

    mrr: float = Field(description="Mean reciprocal rank across keywords.")
    ndcg: float = Field(description="Binary nDCG across keywords.")
    recall_at_k: float = Field(description="Binary recall at k.")
    keyword_coverage: float = Field(description="Percent of keywords found.")


class AnswerEval(BaseModel):
    """LLM-judge result for non-negative answers."""

    feedback: str
    accuracy: float
    completeness: float
    relevance: float


class RefusalEval(BaseModel):
    """LLM-judge result for negative-case refusal behavior."""

    feedback: str
    refusal_correct: float


def _hit(keyword: str, docs: list, k: int) -> float:
    """Return 1/rank when a keyword appears in top-k docs, else 0."""
    for rank, doc in enumerate(docs[:k], start=1):
        if keyword.lower() in doc.page_content.lower():
            return 1.0 / rank
    return 0.0


def evaluate_retrieval(test: TestQuestion, docs: list, k: int = 10) -> RetrievalEval:
    """Score retrieval using keyword hits against retrieved chunk text."""
    if test.category == QuestionCategory.NEGATIVE:
        return RetrievalEval(mrr=0.0, ndcg=0.0, recall_at_k=0.0, keyword_coverage=100.0)
    hits = [_hit(keyword, docs, k) for keyword in test.keywords]
    relevances = [
        [1 if _hit(keyword, [doc], 1) else 0 for doc in docs[:k]]
        for keyword in test.keywords
    ]
    ndcgs = []
    for rel in relevances:
        dcg = sum(value / math.log2(i + 2) for i, value in enumerate(rel))
        idcg = sum(
            value / math.log2(i + 2)
            for i, value in enumerate(sorted(rel, reverse=True))
        )
        ndcgs.append(dcg / idcg if idcg else 0.0)
    found = sum(score > 0 for score in hits)
    return RetrievalEval(
        mrr=sum(hits) / len(hits),
        ndcg=sum(ndcgs) / len(ndcgs),
        recall_at_k=float(found > 0),
        keyword_coverage=found / len(test.keywords) * 100,
    )


def _judge(test: TestQuestion, answer_md: str, model_cls: type[BaseModel]) -> BaseModel:
    """Run the category-aware LLM judge for one generated answer."""
    focus = {
        QuestionCategory.MULTI_DOC: "Weight completeness most heavily.",
        QuestionCategory.SPECIFIC_FACT: "Weight accuracy most heavily.",
        QuestionCategory.EXISTENCE: "Weight completeness over wording polish.",
        QuestionCategory.NEGATIVE: "Pass only when the answer clearly refuses and does not invent facts.",
    }[test.category]
    prompt = (
        f"Question:\n{test.question}\n\nGenerated Answer:\n{answer_md}\n\nReference Answer:\n{test.reference_answer}\n\n"
        f"Category: {test.category.value}\n{focus}"
    )
    response = completion(
        model=JUDGE_MODEL,
        messages=[
            {"role": "system", "content": "Evaluate the answer against the reference."},
            {"role": "user", "content": prompt},
        ],
        response_format=model_cls,
    )
    return model_cls.model_validate_json(response.choices[0].message.content)


def evaluate_case(test: TestQuestion, k: int = 10) -> dict:
    """Run retrieval plus answer/refusal grading for a single eval case."""
    docs = get_retriever(top_k=k).invoke(
        test.question
    )  # get the documents based on the question's query.
    retrieval = evaluate_retrieval(test, docs, k)
    answer_md = "I couldn't find this in your notes."  # if no docs is found, means the negative case is true, so this is our default answer.
    if docs:
        answer_md = (
            completion(model=ANSWER_MODEL, messages=build_prompt(test.question, docs))
            .choices[0]
            .message.content.strip()
        )
    judge = _judge(
        test,
        answer_md,
        RefusalEval if test.category == QuestionCategory.NEGATIVE else AnswerEval,
    )
    return {"test": test, "retrieval": retrieval, "answer": answer_md, "judge": judge}


def summarize_results(results: list[dict]) -> dict:
    """Aggregate retrieval and judge metrics overall and by category."""
    grouped = defaultdict(list)
    for result in results:
        grouped[result["test"].category.value].append(result)
    summary = {}
    for label, rows in {"overall": results, **grouped}.items():
        retrieval = [row["retrieval"] for row in rows]
        judges = [row["judge"] for row in rows]
        summary[label] = {
            "count": len(rows),
            "mrr": sum(row.mrr for row in retrieval) / len(retrieval),
            "ndcg": sum(row.ndcg for row in retrieval) / len(retrieval),
            "recall_at_k": sum(row.recall_at_k for row in retrieval) / len(retrieval),
            "keyword_coverage": sum(row.keyword_coverage for row in retrieval)
            / len(retrieval),
            "accuracy": sum(getattr(row, "accuracy", 0.0) for row in judges)
            / len(judges),
            "completeness": sum(getattr(row, "completeness", 0.0) for row in judges)
            / len(judges),
            "relevance": sum(getattr(row, "relevance", 0.0) for row in judges)
            / len(judges),
            "refusal_correct": sum(
                getattr(row, "refusal_correct", 0.0) for row in judges
            )
            / len(judges),
        }
    return summary


def load_and_evaluate(k: int = 10) -> dict:
    """Load tests, evaluate each case, and return aggregated metrics."""
    return summarize_results([evaluate_case(test, k=k) for test in load_tests()])
