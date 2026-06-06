from pydantic import BaseModel, ConfigDict, EmailStr
from typing import Optional, List, Any
from datetime import datetime

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    role: str
    full_name: Optional[str] = None
    group: str | None = None

    model_config = ConfigDict(from_attributes=True)

class UserResponse(BaseModel):
    id: int
    email: EmailStr
    is_active: bool
    role: str
    group: str | None = None
    full_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class UpdateMe(BaseModel):
    full_name: Optional[str] = None
    group: str | None = None

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshRequest(BaseModel):
    refresh_token: str

class UserAdminUpdate(BaseModel):
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None
    role: Optional[str] = None

class PostCreate(BaseModel):
    title: str
    body: str

class PostResponse(BaseModel):
    id: int
    title: str
    body: str
    user_id: int
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class ChatCreate(BaseModel):
    name: str

class ChatResponse(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)

class MessageCreate(BaseModel):
    content: str

class CriterionIn(BaseModel):
    name: str
    weight: int
    description: Optional[str] = None

class AssignmentCreate(BaseModel):
    class_id: int
    title: str
    description: Optional[str] = None
    criteria: List[CriterionIn]
    max_score: int = 100
    deadline: Optional[datetime] = None
    reference_solution_url: Optional[str] = None

class AssignmentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    criteria: Optional[List[CriterionIn]] = None
    max_score: Optional[int] = None
    deadline: Optional[datetime] = None
    is_active: Optional[bool] = None
    reference_solution_url: Optional[str] = None

class AssignmentResponse(BaseModel):
    id: int
    class_id: int
    title: str
    description: Optional[str] = None
    criteria: str
    max_score: int
    deadline: Optional[datetime] = None
    created_at: datetime
    is_active: bool
    created_by: int
    reference_solution_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class SubmissionCreate(BaseModel):
    text_content: Optional[str] = None
    file_url: Optional[str] = None
    file_urls: Optional[List[str]] = None

class SubmissionResponse(BaseModel):
    id: int
    assignment_id: int
    student_id: int
    file_url: Optional[str] = None
    file_urls: Optional[str] = None
    text_content: Optional[str] = None
    variant_number: Optional[int] = None
    submitted_at: datetime
    status: str
    student_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class SubmissionWithGrade(SubmissionResponse):
    grade: Optional["GradeResponse"] = None

    model_config = ConfigDict(from_attributes=True)

class GradeCreate(BaseModel):
    score: int
    feedback: Optional[str] = None
    criteria_scores: Optional[List[Any]] = None
    graded_by: str = "ai"

class GradeResponse(BaseModel):
    id: int
    submission_id: int
    score: int
    feedback: Optional[str] = None
    criteria_scores: Optional[str] = None
    graded_at: datetime
    graded_by: str

    model_config = ConfigDict(from_attributes=True)

SubmissionWithGrade.model_rebuild()

class RagIngestResponse(BaseModel):
    document_id: int
    filename: str
    chunks_created: int

class RagQueryRequest(BaseModel):
    question: str
    top_k: Optional[int] = None

class RagChunkSource(BaseModel):
    document_id: int
    filename: str
    chunk_index: int
    text_preview: str

class RagQueryResponse(BaseModel):
    answer: str
    sources: List[RagChunkSource]
    context_tokens: int

class ProcessedDocumentResponse(BaseModel):
    id: int
    rag_document_id: Optional[int]
    filename: str
    format: str
    token_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ClassCreate(BaseModel):
    name: str
    description: Optional[str] = None
    group: Optional[str] = None

class ClassUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    group: Optional[str] = None

class ClassResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    created_by: int
    created_at: datetime
    is_active: bool
    group: Optional[str] = None
    member_count: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

class ClassMemberAdd(BaseModel):
    user_id: int

class VariantCreate(BaseModel):
    variant_number: int
    title: Optional[str] = None
    reference_solution_url: str

class VariantResponse(BaseModel):
    id: int
    assignment_id: int
    variant_number: int
    title: Optional[str] = None
    reference_solution_url: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class AssignmentResponseFull(AssignmentResponse):
    variants: List[VariantResponse] = []

    model_config = ConfigDict(from_attributes=True)

class SubmissionCreateV2(BaseModel):
    text_content: Optional[str] = None
    file_url: Optional[str] = None
    file_urls: Optional[List[str]] = None
    variant_number: Optional[int] = None

class StudentRatingEntry(BaseModel):
    student_id: int
    email: str
    full_name: Optional[str] = None
    total_score: int
    graded_count: int
    avg_score: float

class StudentRatingResponse(BaseModel):
    class_id: Optional[int] = None
    ratings: List[StudentRatingEntry]