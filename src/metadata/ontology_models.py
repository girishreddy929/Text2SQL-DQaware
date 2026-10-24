"""src/metadata/ontology_models.py: Pydantic models for Business Ontology."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

TermType = Literal["metric", "concept", "dimension"]
ReviewStatus = Literal["draft", "approved", "rejected"]


def slug(text: str) -> str:
    """Convert term name to lowercase snake_case identifier."""
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")


def make_term_id(source_id: str, term_type: TermType, term_name: str) -> str:
    """Generate deterministic ontology term ID."""
    return f"{source_id}:{term_type}:{slug(term_name)}"


class OntologyTerm(BaseModel):
    source_id: str
    term_name: str
    term_type: TermType
    definition: str
    sql_expression: str
    base_table: str
    mapped_columns: list[str] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)
    status: ReviewStatus = "draft"
    term_id: str = ""

    def model_post_init(self, __context: Any) -> None:  # noqa: PYI063
        if not self.term_id:
            object.__setattr__(
                self,
                "term_id",
                make_term_id(self.source_id, self.term_type, self.term_name),
            )


class OntologyFile(BaseModel):
    source_id: str
    terms: list[OntologyTerm]

    @model_validator(mode="before")
    @classmethod
    def propagate_source_id(cls, data: Any) -> Any:
        """Propagate top-level source_id down to child terms."""
        if isinstance(data, dict):
            sid = data.get("source_id", "")
            for t in data.get("terms", []):
                if isinstance(t, dict) and not t.get("source_id"):
                    t["source_id"] = sid
        return data
