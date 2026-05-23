import json
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TEST_FILE = Path(__file__).with_name("tests.jsonl")


class QuestionCategory(StrEnum):
    """Supported eval question shapes."""

    EXISTENCE = "existence"
    MULTI_DOC = "multi_doc"
    SPECIFIC_FACT = "specific_fact"
    NEGATIVE = "negative"


class TestQuestion(BaseModel):
    """Validated eval case loaded from JSONL."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(description="Question sent to the RAG system.")
    category: QuestionCategory = Field(
        description="Question shape for scoring."
    )  # pydantic helps us convert this into an enum category="negative" becomes QuestionCategory.NEGATIVE, even though there is no specific field_validator, pydantic still checks that the value is string and a member of the enum, due to the type 'StrEnum'
    keywords: list[str] = Field(description="Terms expected in retrieved chunks.")
    reference_answer: str = Field(description="Expected answer or refusal text.")
    expected_source_ids: list[str] | None = Field(
        default=None,
        description="Optional page IDs expected to appear in retrieval.",
    )

    @field_validator("question", "reference_answer")
    @classmethod
    def validate_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("keywords", "expected_source_ids")
    @classmethod
    def validate_string_list(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [item.strip() for item in value if item.strip()]
        return cleaned or None

    """
    @model_validator(mode="after") is a Pydantic v2 hook that runs after Pydantic has already parsed and validated the individual fields. This matters because when the category is negative, then we need to ensure that the keywords is empty.
    Why 'after': By that point, category is already a QuestionCategory enum, not just a raw string. keywords and expected_source_ids have already gone through their field validators. So this validator can safely enforce cross-field rules on the finished model. The TestQuestion pydantic object has already been created.
    """

    @model_validator(mode="after")
    def validate_category_rules(self) -> "TestQuestion":
        if self.category == QuestionCategory.NEGATIVE:
            if self.keywords:
                raise ValueError("negative questions must not define keywords")
            if self.expected_source_ids:
                raise ValueError("negative questions must not define source ids")
            return self
        if not self.keywords:
            raise ValueError("non-negative questions must define at least one keyword")
        return self


def load_tests(path: str | Path = TEST_FILE) -> list[TestQuestion]:
    """Load and validate eval cases from a JSONL file."""
    tests = []
    path = Path(path)
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                tests.append(TestQuestion.model_validate(payload))
            except Exception as exc:
                raise ValueError(f"{path}:{line_number} is invalid: {exc}") from exc
    return tests
