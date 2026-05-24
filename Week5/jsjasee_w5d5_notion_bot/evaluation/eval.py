import math
import os
import sys
from collections import defaultdict
from multiprocessing import Pool

from dotenv import load_dotenv
from litellm import completion
from pydantic import BaseModel, Field
from tenacity import retry, wait_exponential
from tqdm import tqdm

from answer import ANSWER_MODEL, build_prompt, get_retriever
from evaluation.test import QuestionCategory, TestQuestion, load_tests

load_dotenv(override=True)
JUDGE_MODEL = os.getenv("EVAL_JUDGE_MODEL", "openai/gpt-4.1-nano")
WORKERS = int(os.getenv("EVAL_WORKERS", "5"))
RETRY_WAIT = wait_exponential(multiplier=1, min=10, max=240)


class RetrievalEval(BaseModel):
    """Retrieval metrics computed from retrieved chunk text."""

    mrr: float = Field(description="Mean reciprocal rank across keywords.")
    ndcg: float = Field(description="Binary nDCG across keywords.")
    recall_at_k: float = Field(description="Binary recall at k.")
    keyword_coverage: float = Field(description="Percent of keywords found.")


class AnswerEval(BaseModel):
    """LLM-judge result for non-negative answers."""

    feedback: str
    # ✅ Bound judge scores to the intended 1-5 rubric so invalid outputs fail fast.
    accuracy: float = Field(
        ge=1, le=5
    )  # ge means greater than or equal to, le means less than or equal to
    completeness: float = Field(ge=1, le=5)
    relevance: float = Field(ge=1, le=5)


class RefusalEval(BaseModel):
    """LLM-judge result for negative-case refusal behavior."""

    feedback: str
    # ✅ Refusal correctness is binary: 0 = bad refusal, 1 = correct refusal.
    refusal_correct: float = Field(ge=0, le=1)


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
        # ✅ Make the scoring contract explicit so the judge stays inside the expected range.
        QuestionCategory.MULTI_DOC: "Weight completeness most heavily. Return numeric scores only in the range 1 to 5.",
        QuestionCategory.SPECIFIC_FACT: "Weight accuracy most heavily. Return numeric scores only in the range 1 to 5.",
        QuestionCategory.EXISTENCE: "Weight completeness over wording polish. Return numeric scores only in the range 1 to 5.",
        QuestionCategory.NEGATIVE: "Pass only when the answer clearly refuses and does not invent facts. Return refusal_correct as either 0 or 1 only.",
    }[test.category]
    prompt = (
        f"Question:\n{test.question}\n\nGenerated Answer:\n{answer_md}\n\nReference Answer:\n{test.reference_answer}\n\n"
        f"Category: {test.category.value}\n{focus}"
    )
    response = completion(
        model=JUDGE_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Evaluate the answer against the reference. "
                    "Follow the requested score ranges exactly."
                ),
            },
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


# look at notion for explanation of how evaluate_one_case and evaluate_all_cases work.
@retry(wait=RETRY_WAIT)
def evaluate_one_case(args: tuple[TestQuestion, int]) -> dict:
    """Evaluate one test case inside a pool worker."""
    test, k = args
    return evaluate_case(test, k=k)


def evaluate_all_cases(k: int = 10, progress=None) -> list[dict]:
    """Evaluate all tests in parallel and stream progress to CLI and Gradio."""
    tests = load_tests()
    total = len(tests)
    if not total:
        return []

    results = []
    if progress is not None:
        progress(0, desc="Starting evals...")

    with Pool(processes=WORKERS) as pool:
        iterator = pool.imap_unordered(evaluate_one_case, [(test, k) for test in tests])
        # this iterator behaves like a generator, it will yield one result at a time as the for loop runs through it.
        for index, result in enumerate(
            tqdm(iterator, total=total, desc="Evals", file=sys.stderr, mininterval=0.1),
            start=1,
        ):
            results.append(result)
            if progress is not None:
                progress(index / total, desc=f"Evaluating test {index}/{total}...")
    return results


def summarize_results(results: list[dict]) -> dict:
    """Aggregate retrieval and judge metrics overall and by category."""
    grouped = defaultdict(list)
    # grouped is a dictionary, with values as lists. this allows you to append a key to the dict, even though the key may not be in the dictionary initially, python creates the empty list for you automatically the first time that key is used.
    # you can do grouped[key].append(value), even though key is not in the dict.

    for result in results:
        grouped[result["test"].category.value].append(result)

    negative_judges = [
        row["judge"] for row in grouped.get(QuestionCategory.NEGATIVE.value, [])
    ]
    summary = {}

    print(negative_judges)

    for label, rows in {"overall": results, **grouped}.items():
        retrieval = [row["retrieval"] for row in rows]
        judges = [row["judge"] for row in rows]

        print(judges)

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
            # ✅ Overall refusal correctness should reflect only negative tests, not all categories.
            "refusal_correct": (
                sum(getattr(row, "refusal_correct", 0.0) for row in negative_judges)
                / len(negative_judges)
                if label == "overall" and negative_judges
                else sum(getattr(row, "refusal_correct", 0.0) for row in judges)
                / len(judges)
            ),
            # note that getattr(row, "refusal_correct", 0.0) means for each row in judges, try to read the row.refusal_correct attribute. If it doesn't exist, return 0.0
        }
    return summary


def load_and_evaluate(k: int = 10, progress=None) -> dict:
    """Load tests, evaluate them in parallel, and return aggregated metrics."""
    return summarize_results(evaluate_all_cases(k=k, progress=progress))
