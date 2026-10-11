from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20_000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4_000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=50)


class IngestResponse(BaseModel):
    doc_id: str
    filename: str
    chunks: int


class DeleteResponse(BaseModel):
    doc_id: str
    deleted_chunks: int
