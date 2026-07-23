from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class Category(StrEnum):
    PERSON_NAME = "PERSON_NAME"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    ADDRESS = "ADDRESS"
    SSN = "SSN"
    BANK_ACCOUNT = "BANK_ACCOUNT"
    CREDIT_CARD = "CREDIT_CARD"
    PASSPORT = "PASSPORT"
    DRIVERS_LICENSE = "DRIVERS_LICENSE"
    DATE_OF_BIRTH = "DATE_OF_BIRTH"
    IP_ADDRESS = "IP_ADDRESS"
    URL = "URL"
    API_KEY = "API_KEY"
    PASSWORD = "PASSWORD"
    SECRET = "SECRET"
    COMPANY_INTERNAL = "COMPANY_INTERNAL"
    PROJECT_NAME = "PROJECT_NAME"
    LOCATION = "LOCATION"
    INDIRECT_IDENTIFIER = "INDIRECT_IDENTIFIER"
    OTHER = "OTHER"


class Finding(BaseModel):
    text: str = Field(min_length=1)
    category: Category
    confidence: float = Field(ge=0, le=1)
    source: str = Field(min_length=1)
    sources: set[str] = Field(default_factory=set)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def valid_span(self) -> "Finding":
        if self.end <= self.start or self.end - self.start != len(self.text):
            raise ValueError("finding offsets do not match text length")
        self.sources.add(self.source)
        return self

    def matches(self, original: str) -> bool:
        return self.end <= len(original) and original[self.start : self.end] == self.text
