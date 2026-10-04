from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ExtractedEntry(BaseModel):
    customer_name: str = Field(min_length=1)
    amount_rupees: int | None = Field(default=None, ge=1)
    due_day: str | None = None
    context: str | None = None
    transaction_type: Literal["credit_given", "credit_paid"]
    confidence: float = Field(ge=0, le=1)


class NoteResponse(BaseModel):
    transcript: str
    extracted: ExtractedEntry
    status: Literal["inserted", "review_required"]
    transaction: dict | None = None
    matched_customer: str | None = None
    transcription_provider: str
    extraction_provider: str


class RegisterRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=256)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class UserResponse(BaseModel):
    id: int
    display_name: str
    email: str
