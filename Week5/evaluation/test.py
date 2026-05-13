import json
from pathlib import Path
from pydantic import BaseModel, Field, field_validator

TEST_FILE = str(Path(__file__).parent / "tests.jsonl")


class TestQuestion(BaseModel):
    """A test question with expected keywords and reference answer."""

    question: str = Field(description="The question to ask the RAG system")
    keywords: list[str] = Field(
        description="Keywords that must appear in retrieved context"
    )
    reference_answer: str = Field(description="The reference answer for this question")
    category: str = Field(
        description="Question category (e.g., direct_fact, spanning, temporal)"
    )


def load_tests() -> list[TestQuestion]:
    """Load test questions from JSONL file."""
    tests = []
    with open(TEST_FILE, "r", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line.strip())
            tests.append(TestQuestion(**data))
    return tests


class TestQuestionV2(BaseModel):
    question: str = Field(description="The question to ask the RAG system")
    keywords: list[str]
    reference_answer: str
    category: str

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, keywords_value):
        if not keywords_value:
            raise ValueError("keywords must not be empty")
        return keywords_value

    @field_validator("category")
    @classmethod
    def validate_category(cls, category_value):
        if category_value not in ["direct_fact", "spanning", "temporal"]:
            raise ValueError("category must not be one of the 3 allowed values")
        return category_value


try:
    TestQuestionV2(
        question="Who is Avery?",
        keywords=["Avery"],
        reference_answer="CEO of Insurllm",
        category="something else",
    )
except Exception as e:
    # how to consolidate errors from pydantic
    print(
        e.errors()
    )  # output if category=2 : [{'type': 'string_type', 'loc': ('category',), 'msg': 'Input should be a valid string', 'input': 2, 'url': 'https://errors.pydantic.dev/2.11/v/string_type'}]
    print(
        e.error_count()
    )  # output: 1, because only the category is incorrect data type.
