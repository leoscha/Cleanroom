from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cleanroom.models.finding import Category


class Action(StrEnum):
    REPLACE = "replace"
    REDACT = "redact"
    IGNORE = "ignore"
    REVIEW = "review"


class ReviewBehavior(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quarantine: bool = True
    warn_only: bool = False
    auto_replace: bool = False


class SanitizationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: int = 1
    name: str
    version: int = Field(ge=1)
    description: str = ""
    minimum_confidence: float = Field(ge=0, le=1)
    default_action: Action = Action.IGNORE
    category_confidence: dict[Category, float] = Field(default_factory=dict)
    actions: dict[Category, Action]
    placeholders: dict[Category, str] = Field(default_factory=dict)
    review_behavior: ReviewBehavior = Field(default_factory=ReviewBehavior)
    ollama_prompt_hints: list[str] = Field(default_factory=list)
    verification_strict: bool = True

    @model_validator(mode="after")
    def complete(self) -> "SanitizationPolicy":
        if self.schema_version != 1:
            raise ValueError(f"unsupported policy schema_version: {self.schema_version}")
        for category in Category:
            self.actions.setdefault(category, self.default_action)
            self.placeholders.setdefault(category, category.value)
        for category, confidence in self.category_confidence.items():
            if not 0 <= confidence <= 1:
                raise ValueError(f"confidence for {category.value} must be between 0 and 1")
        if self.review_behavior.warn_only and self.review_behavior.quarantine:
            raise ValueError("review behavior cannot both warn and quarantine")
        return self

    def threshold_for(self, category: Category) -> float:
        return self.category_confidence.get(category, self.minimum_confidence)
