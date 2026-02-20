import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import List, Dict, Any, Optional

from pydantic import BaseModel as PydanticBaseModel
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB

# ==========================================
# 0. HELPERS
# ==========================================
def utc_now():
    return datetime.now(timezone.utc)

# ==========================================
# 1. ENUMS (Shared Constraints)
# ==========================================

class ModelCategory(str, Enum):
    UTILITY = "utility"             # e.g. Watermelon Thumper
    DIAGNOSTIC = "diagnostic"       # e.g. Engine Sound Analyzer
    PERFORMANCE = "performance"     # e.g. NPU Benchmarks
    FUN = "fun"                     # e.g. Dog Breed Identifier
    OTHER = "other"

class AssetType(str, Enum):
    TFLITE = "tflite"
    LABEL_TXT = "label_txt"
    VOCAB_TXT = "vocab_txt"
    CONFIG_JSON = "config_json"

class DevicePlatform(str, Enum):
    ANDROID = "android"
    IOS = "ios"

class LicenseType(str, Enum):
    # --- The "Green Light" (Safe for Commercial) ---
    APACHE_2_0 = "apache-2.0"
    MIT = "mit"
    BSD = "bsd"             # Generic BSD family
    BSD_3_CLAUSE = "bsd-3-clause"
    BSD_3_CLAUSE_CLEAR = "bsd-3-clause-clear"
    CC0_1_0 = "cc0-1.0"     # Public Domain
    AFL_3_0 = "afl-3.0"     # Academic Free License

    # --- The "Yellow Light" (Attribution / Restrictions) ---
    CC_BY_4_0 = "cc-by-4.0"
    CC_BY_SA_3_0 = "cc-by-sa-3.0"
    CC_BY_SA_4_0 = "cc-by-sa-4.0"
    OPENRAIL = "openrail"
    OPENRAIL_M = "openrail++" # Often used for Stable Diffusion variants
    
    # --- The "Red Light" (Non-Commercial / Copyleft) ---
    CC_BY_NC_4_0 = "cc-by-nc-4.0"
    CC_BY_NC_SA_4_0 = "cc-by-nc-sa-4.0"
    CC_BY_NC_ND_4_0 = "cc-by-nc-nd-4.0"
    GPL_3_0 = "gpl-3.0"
    AGPL_3_0 = "agpl-3.0"
    LLAMA_2 = "llama2"      # Meta's custom license
    LLAMA_3 = "llama3"      # Meta's custom license
    
    # --- Fallback ---
    OTHER = "other"
    UNKNOWN = "unknown"

    @property
    def is_commercial_allowed(self) -> bool:
        """
        Helper to determine if this license generally allows commercial use.
        NOTE: This is a heuristic, not legal advice.
        """
        SAFE_LICENSES = {
            LicenseType.APACHE_2_0, 
            LicenseType.MIT, 
            LicenseType.BSD,
            LicenseType.BSD_3_CLAUSE,
            LicenseType.BSD_3_CLAUSE_CLEAR,
            LicenseType.CC0_1_0,
            LicenseType.AFL_3_0,
            LicenseType.CC_BY_4_0, # Allowed, but requires attribution
            LicenseType.OPENRAIL, # Usually allowed with restrictions
            LicenseType.OPENRAIL_M,
        }
        return self in SAFE_LICENSES
    

# ==========================================
# 2. JSON COMPONENTS (The "Inner" Data)
# ==========================================
# These are used for Validation in API Requests/Responses

class PipelineStep(PydanticBaseModel):
    step_name: str
    params: Dict[str, Any] = {}

class PipelineConfig(PydanticBaseModel):
    input_nodes: List[str]
    output_nodes: List[str]
    pre_processing: List[PipelineStep] = []
    post_processing: List[PipelineStep] = []
    asset_map: Dict[str, str] = {}

class MLModelAsset(PydanticBaseModel):
    asset_key: str
    asset_type: AssetType
    source_url: str 
    file_size_bytes: int
    file_hash: str 
    is_hosted_by_us: bool = False

# ==========================================
# 3. USER ENTITY
# ==========================================

class UserBase(SQLModel):
    username: str = Field(index=True, unique=True)
    email: str = Field(index=True, unique=True)
    is_developer: bool = False
    # FIX: Use helper function for time
    created_at: datetime = Field(default_factory=utc_now)
    hf_username: Optional[str] = Field(default=None, index=True)
    hf_verification_token: Optional[str] = Field(default=None)
    hf_access_token: Optional[str] = Field(default=None)

class UserDB(UserBase, table=True):
    __tablename__ = "users"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    
    # Relationships
    models: List["MLModelDB"] = Relationship(back_populates="author")

class UserRead(UserBase):
    id: uuid.UUID

# ==========================================
# 4. ML MODEL ENTITY (The "Product")
# ==========================================

class MLModelBase(SQLModel):
    name: str
    slug: Optional[str] = Field(index=True, unique=True)
    description: Optional[str] = None
    category: ModelCategory = Field(default=ModelCategory.UTILITY)
    license_type: str = Field(nullable=False, default=LicenseType.UNKNOWN) # Default to UNKNOWN for safety
    origin_repo_url: Optional[str] = None

class MLModelDB(MLModelBase, table=True):
    __tablename__ = "ml_models"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    author_id: uuid.UUID = Field(foreign_key="users.id")
    hf_model_id: Optional[str] = Field(default=None, index=True)
    is_verified_official: bool = False
    
    # FIX: Use default_factory for mutable list
    tags: List[str] = Field(sa_column=Column(JSONB), default_factory=list)
    # Stores "image-classification", "text-generation", etc.
    # We use a string so we don't crash if HF introduces a new task.
    task: Optional[str] = Field(default=None, index=True)
    
    # Metrics
    total_download_count: int = 0  
    rating_weighted_avg: float = 0.0
    total_ratings: int = 0
    created_at: datetime = Field(default_factory=utc_now)
    
    # Relationships
    author: UserDB = Relationship(back_populates="models")
    versions: List["ModelVersionDB"] = Relationship(back_populates="model")

class MLModelCreate(MLModelBase):
    description: str
    tags: List[str] = Field(default_factory=list)

class MLModelRead(MLModelBase):
    id: uuid.UUID
    author_id: uuid.UUID
    description: str
    tags: List[str]
    total_download_count: int
    total_ratings: int
    # FIX: Renamed to match DB column exactly
    rating_weighted_avg: float 
    created_at: datetime

# ==========================================
# 5. MODEL VERSION ENTITY (The "Logic")
# ==========================================

class ModelVersionBase(SQLModel):
    version_string: str = Field(index=True) # "1.0.0"
    changelog: Optional[str] = None

class ModelVersionDB(ModelVersionBase, table=True):
    __tablename__ = "model_versions"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    model_id: uuid.UUID = Field(foreign_key="ml_models.id")
    # Stores the specific git commit hash (e.g. "9a3f2b...")
    # This ensures we know exactly which version of the file we are pointing to
    hf_commit_sha: Optional[str] = None
    
    # Typed as generic Dict/List for SQL storage safety
    # We trust the 'Create' model to validate the structure before saving
    pipeline_spec: Dict[str, Any] = Field(sa_column=Column(JSONB))
    assets: List[Dict[str, Any]] = Field(sa_column=Column(JSONB))
    
    published_at: datetime = Field(default_factory=utc_now)
    download_count: int = 0
    num_ratings: int = 0
    rating_avg: float = 0
        
    # Relationships
    model: MLModelDB = Relationship(back_populates="versions")
    logs: List["InferenceLogDB"] = Relationship(back_populates="version")

class ModelVersionCreate(ModelVersionBase):
    # Strict validation happens here on input
    pipeline_spec: PipelineConfig
    assets: List[MLModelAsset]

class ModelVersionRead(ModelVersionBase):
    id: uuid.UUID
    model_id: uuid.UUID
    # Strict validation happens here on output
    pipeline_spec: PipelineConfig
    assets: List[MLModelAsset]
    published_at: datetime
    download_count: int
    num_ratings: int
    rating_avg: float

# ==========================================
# 6. TELEMETRY
# ==========================================

class InferenceLogDB(SQLModel, table=True):
    __tablename__ = "inference_logs"
    id: Optional[int] = Field(default=None, primary_key=True) # BigInt auto-increment
    model_version_id: uuid.UUID = Field(foreign_key="model_versions.id")
    timestamp: datetime = Field(default_factory=utc_now, index=True)
    
    device_model: str
    platform: DevicePlatform
    total_inference_ms: int
    success: bool
    
    version: ModelVersionDB = Relationship(back_populates="logs")

class InferenceLogCreate(SQLModel):
    device_model: str
    platform: DevicePlatform
    total_inference_ms: int
    success: bool

# ==========================================
# 7. SPECIAL API RESPONSES
# ==========================================

class ModelManifestResponse(PydanticBaseModel):
    id: uuid.UUID
    name: str
    version: str
    assets: List[MLModelAsset]
    pipeline: PipelineConfig