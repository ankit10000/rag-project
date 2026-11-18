"""Request/response schemas (pydantic v2)."""

from typing import Literal, Optional

from pydantic import BaseModel, Field



class ComponentStatus(BaseModel):
    name: str
    status: Literal["configured", "initialized", "available", "unavailable", "not_checked"]
    detail: str = ""


class HealthResponse(BaseModel):
    status: Literal["ok"]


class SystemStatusResponse(BaseModel):
    app_version: str
    api_version: str
    components: list[ComponentStatus]


class DocumentSummary(BaseModel):
    document_name: str
    chunks: int
    pages: int


class DocumentPage(BaseModel):
    page_number: int
    chunks: int


class DocumentDetail(DocumentSummary):
    status: Literal["indexed"]
    page_breakdown: list[DocumentPage]


class IngestResponse(BaseModel):
    document_name: str
    status: Literal["indexed"]
    chunks: int
    replaced: bool


class Citation(BaseModel):
    ref: Optional[str] = None
    document: Optional[str] = None
    page: Optional[int] = None
    chunk_id: Optional[int] = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    request_id: Optional[str]
    conversation_id: str
    kind: Literal["answer", "memory_deletion"]
    answer: str
    status: Optional[str] = None
    citations: list[Citation] = []
    memory_extraction: Optional[str] = None
    summary_update: Optional[str] = None
    deleted_count: Optional[int] = None


class ConversationCreate(BaseModel):
    title: str = Field(default="New Conversation", min_length=1, max_length=200)


class ConversationSummary(BaseModel):
    conversation_id: str
    title: Optional[str] = None
    message_count: int


class Message(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    content: str


class ConversationDetail(BaseModel):
    conversation_id: str
    messages: list[Message]
    note: str = "Messages excluded after a memory deletion are not shown."


class MemoryItem(BaseModel):
    memory_id: int
    memory: str
    category: str
    provenance: Literal["USER_SUPPORTED"]
    source_message_ids: list[int]


class MemoryList(BaseModel):
    conversation_id: str
    memories: list[MemoryItem]
    unverified_hidden: int
    note: str = ("Only memories with a verified same-conversation user source are listed; "
                 "unverified/unsupported memories are counted, not shown.")


class MemorySource(BaseModel):
    message_id: int
    role: Optional[str]
    link_kind: Optional[str]


class ProviderInfo(BaseModel):
    name: str
    implemented: bool
    api_key_configured: bool
    primary_model: Optional[str]
    fallback_models: list[str]
    settings_source: dict


class ProvidersResponse(BaseModel):
    providers: list[ProviderInfo]
    write_support: bool = False
    note: str


class MetricsResponse(BaseModel):
    enabled: bool
    timings: dict
    counters: dict
    note: str


class DeletionResponse(BaseModel):
    resource: Literal["conversation", "message", "memory"]
    conversation_id: str
    deleted: bool
    message_id: Optional[int] = None
    memory_id: Optional[int] = None
    orphaned_memory_ids: list[int] = Field(default_factory=list)
    still_supported_memory_ids: list[int] = Field(default_factory=list)
    cleanup_status: Optional[Literal['source_fenced', 'incomplete_unknown_provenance']] = None
