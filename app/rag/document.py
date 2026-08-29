"""RAG 领域数据模型。"""

from math import isfinite
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _RAGModel(BaseModel):
    """为 RAG 值对象提供严格、不可变的公共配置。"""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )


class Document(_RAGModel):
    """从一个知识源加载得到的完整文档。"""

    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    text: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Document text 不能为空")
        return value


class Chunk(_RAGModel):
    """保留文档来源和 Token 区间的最小检索单元。"""

    id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    text: str = Field(min_length=1)
    index: int = Field(ge=0)
    token_count: int = Field(gt=0)
    start_token: int = Field(ge=0)
    end_token: int = Field(gt=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_token_range(self) -> "Chunk":
        if self.end_token <= self.start_token:
            raise ValueError("end_token 必须大于 start_token")
        if self.token_count != self.end_token - self.start_token:
            raise ValueError("token_count 必须等于 end_token - start_token")
        return self


class RetrievedChunk(_RAGModel):
    """检索路径返回的带排名 Chunk。"""

    chunk: Chunk
    score: float
    retrieval_method: str = Field(min_length=1)
    rank: int = Field(ge=1)

    @field_validator("score")
    @classmethod
    def score_must_be_finite(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("score 必须是有限数值")
        return value
