"""Bounded v2 input contracts; no client may submit an owner or storage path."""
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
class Input(BaseModel):
    model_config=ConfigDict(extra='forbid')
class Credentials(Input):
    email:str=Field(max_length=254)
    password:str=Field(min_length=1,max_length=1024)
class Registration(Credentials):
    display_name:str=Field(default='',max_length=100)
class ConversationInput(Input):
    title:str=Field(default='New conversation',min_length=1,max_length=200)
class ChatInput(Input):
    conversation_id:UUID
    turn_id:UUID|None=None
    message:str=Field(min_length=1,max_length=20000)
class UserUpdate(Input):
    role:str|None=None
    status:str|None=None
class PasswordReset(Input):
    password:str=Field(min_length=12,max_length=1024)

class UserOut(BaseModel):
    id:UUID
    email:str
    display_name:str
    role:str
    status:str
class DocumentOut(BaseModel):
    id:UUID
    filename:str
    status:str
    pages:int
    chunks:int
    created_at:datetime
    page_metadata:list[dict]
class UploadOut(BaseModel):
    id:UUID
    document_id:UUID
    job_id:UUID
    filename:str
    status:str
class JobOut(BaseModel):
    id:UUID
    document_id:UUID
    status:str
    attempts:int
    error_code:str|None
    created_at:datetime
    progress:int
    heartbeat_at:datetime|None
    lease_until:datetime|None
class ConversationOut(BaseModel):
    conversation_id:UUID
    title:str
    message_count:int=0
class MessageOut(BaseModel):
    turn_id:UUID|None=None
    answer_metadata:'ChatOut|None'=None
    id:int
    role:str
    content:str
class HistoryOut(BaseModel):
    conversation_id:UUID
    messages:list[MessageOut]
class CitationOut(BaseModel):
    ref:str|None=None
    document:str
    document_id:UUID
    page:int
    chunk_id:int|None=None
class ChatOut(BaseModel):
    model_config=ConfigDict(extra='allow')
    conversation_id:UUID
    kind:str
    answer:str
    status:str|None=None
    answer_status:str|None=None
    citations:list[CitationOut]=[]
class MemoryOut(BaseModel):
    memory_id:int
    memory:str
    category:str
    provenance:str
    source_message_ids:list[int]
class MemoryListOut(BaseModel):
    conversation_id:UUID
    memories:list[MemoryOut]
    unverified_hidden:int
