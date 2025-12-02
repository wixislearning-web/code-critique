from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

# ============================================================================
# ENUMS
# ============================================================================

class ReviewStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class Severity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"

class FeedbackCategory(str, Enum):
    SECURITY = "security"
    QUALITY = "quality"
    ARCHITECTURE = "architecture"

class SubscriptionTier(str, Enum):
    FREE = "free"
    PRO = "pro"
    TEAM = "team"

# ============================================================================
# REQUEST MODELS
# ============================================================================

class GitHubOAuthRequest(BaseModel):
    code: str

class ReviewRequest(BaseModel):
    repo_full_name: str
    context: Optional[str] = None
    focus_areas: List[str] = Field(default=["security", "quality", "architecture"])

class UpdateUserPreferencesRequest(BaseModel):
    email: Optional[EmailStr] = None
    notification_enabled: Optional[bool] = None
    preferred_languages: Optional[List[str]] = None

# ============================================================================
# RESPONSE MODELS
# ============================================================================

class GitHubOAuthResponse(BaseModel):
    access_token: str
    user_id: str
    github_username: str
    avatar_url: Optional[str] = None
    email: Optional[str] = None

class Repository(BaseModel):
    id: int
    name: str
    full_name: str
    description: Optional[str] = None
    html_url: str
    language: Optional[str] = None
    updated_at: str
    private: bool
    stars: int = 0
    forks: int = 0

class FeedbackItem(BaseModel):
    category: str
    severity: str
    title: str
    description: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    code_snippet: Optional[str] = None
    suggestion: str
    reasoning: str

class ReviewScores(BaseModel):
    security: int = Field(ge=0, le=10)
    quality: int = Field(ge=0, le=10)
    architecture: int = Field(ge=0, le=10)
    overall: Optional[int] = Field(ge=0, le=10, default=None)

class Review(BaseModel):
    id: str
    user_id: str
    repo_name: str
    repo_full_name: str
    status: str
    context: Optional[str] = None
    focus_areas: List[str]
    feedback: Optional[List[FeedbackItem]] = None
    scores: Optional[Dict[str, int]] = None
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

class ReviewSummary(BaseModel):
    id: str
    repo_name: str
    repo_full_name: str
    status: str
    scores: Optional[Dict[str, int]] = None
    feedback_count: Optional[int] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

class User(BaseModel):
    id: str
    github_id: str
    github_username: str
    email: Optional[EmailStr] = None
    avatar_url: Optional[str] = None
    subscription_tier: str = "free"
    reviews_count: int = 0
    created_at: datetime
    last_login: datetime

class UserStats(BaseModel):
    total_reviews: int
    reviews_this_month: int
    reviews_remaining: int
    average_security_score: float
    average_quality_score: float
    average_architecture_score: float
    improvement_trend: str

class Subscription(BaseModel):
    id: str
    user_id: str
    tier: str
    reviews_used_this_month: int
    reviews_limit: int
    subscription_start: datetime
    subscription_end: Optional[datetime] = None
    is_active: bool = True

# ============================================================================
# INTERNAL MODELS
# ============================================================================

class RepositoryFile(BaseModel):
    path: str
    content: str
    size: int
    language: Optional[str] = None

class RepositoryData(BaseModel):
    repo_full_name: str
    files: List[RepositoryFile]
    file_count: int
    total_size: int
    primary_language: Optional[str] = None
    languages: Dict[str, int] = {}

class AIAnalysisRequest(BaseModel):
    repo_data: RepositoryData
    focus_areas: List[str]
    context: Optional[str] = None

# ============================================================================
# HEALTH CHECK
# ============================================================================

class HealthCheck(BaseModel):
    status: str
    timestamp: datetime
    version: str = "1.0.0"
    database_connected: bool
    ai_service_available: bool