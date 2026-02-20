from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from enum import Enum
from typing import List, Dict, Any, Optional
import uuid
from datetime import datetime, UTC
from fastapi.middleware.cors import CORSMiddleware
import sqlalchemy
import os
import logging
from huggingface_hub import HfApi, hf_hub_url
import requests
from functools import lru_cache
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from schema import ModelCategory, AssetType, DevicePlatform, LicenseType, PipelineConfig, MLModelAsset, MLModelDB, UserDB, ModelVersionDB
from database import engine, get_session
from sqlmodel import Field, Session, SQLModel, create_engine, select
from auth import get_current_user
from hf_sync import run_sync
from config import get_settings

# get .env configs
settings = get_settings()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# user DTOs
# user get
class UsersResponse(BaseModel):
    id: uuid.UUID
    username: str
    email: str
    is_developer: bool
    created_at: datetime
    hf_username: Optional[str]
    hf_verification_token: Optional[str] = None
    hf_access_token: Optional[str] = None

    class Config:
        from_attributes = True

# user post
class UsersCreate(BaseModel):
    username: str
    email: str
    hf_username: Optional[str]

# user put
class UsersUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    hf_username: Optional[str] = None

# model DTOs
# model get
class ModelResponse(BaseModel):
    name: str
    slug: Optional[str] = None
    description: str | None
    category: ModelCategory
    id: uuid.UUID
    author_id: uuid.UUID
    tags: List[str]
    task: str | None
    license_type: LicenseType
    total_download_count: int
    rating_weighted_avg: float
    total_ratings: int
    created_at: datetime

# model post
class ModelCreate(BaseModel):
    name: str
    slug: Optional[str] = None
    hf_model_id: Optional[str] = None
    description: str | None = None
    category: ModelCategory
    tags: Optional[List[str]] = None
    task: Optional[str] = None

# model put
class ModelUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    hf_model_id: Optional[str] = None
    description: Optional[str | None] = None
    category: Optional[ModelCategory] = None
    tags: Optional[List[str]] = None
    task: Optional[str] = None
    total_download_count: Optional[int] = None

# model version DTOs
# model version get
class ModelVerResponse(BaseModel):
    id: uuid.UUID
    version_string: str
    changelog: Optional[str]
    model_id: uuid.UUID
    hf_commit_sha: Optional[str] = None
    
    # COMPLEX JSONB COLUMNS
    pipeline_spec: PipelineConfig
    assets: List[MLModelAsset]
    
    # Telemetry Aggregates
    published_at: datetime
    download_count: int
    num_ratings: int
    rating_avg: float

# model version post
class ModelVerCreate(BaseModel):
    id: uuid.UUID
    model_id: uuid.UUID
    pipeline_spec: PipelineConfig
    assets: List[MLModelAsset]
    hf_commit_sha: Optional[str] = None

# model version put
class ModelVerUpdate(BaseModel):
    id: uuid.UUID
    model_id: uuid.UUID
    hf_commit_sha: Optional[str] = None
    pipeline_spec: Optional[PipelineConfig] = None
    assets: Optional[List[MLModelAsset]] = None
    download_count: Optional[int] = None
    num_ratings: Optional[int] = None
    rating_avg: Optional[float] = None

# Input DTO for the HF Import Request
class HFImportRequest(BaseModel):
    hf_id: str # e.g. "google/mobilenet_v2_1.0_224"


# Initialize App
app = FastAPI(
    title="Pocket AI Lab API",
    version="1.0.0",
    openapi_tags = [
        {
            "name": "Users",
        },
        {
            "name": "Models",
        },
        {
            "name": "Model Versions",
        },
        {
            "name": "Hugging Face",
        }
    ]
)

# CORS
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
    expose_headers=["Content-Type", "Authorization"],
    max_age=3600,
)

# ==========================================
# SCHEDULER SETUP
# ==========================================
# Initialize the background scheduler for HuggingFace model sync
scheduler = BackgroundScheduler()

@app.on_event("startup")
def start_scheduler():
    """Start the background scheduler when FastAPI starts."""
    if not scheduler.running:
        # Schedule the HF sync job to run daily at 2 AM UTC
        scheduler.add_job(
            run_sync,
            CronTrigger(hour=2, minute=0),  # 2 AM UTC daily
            id='hf_litert_sync',
            name='HuggingFace LiteRT Model Sync',
            replace_existing=True,
            misfire_grace_time=600,  # Allow up to 10 minutes for missed executions
        )
        scheduler.start()
        logger.info("Background scheduler started - HF LiteRT sync scheduled for 02:00 UTC daily")

@app.on_event("shutdown")
def stop_scheduler():
    """Stop the scheduler when FastAPI shuts down."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Background scheduler shut down")

# 1. Cache the valid tasks from HF (Refresh once per day/hour)
@lru_cache(maxsize=1)
def get_valid_hf_tasks():
    try:
        resp = requests.get("https://huggingface.co/api/tasks")
        if resp.status_code == 200:
            # Returns a dict where keys are task IDs
            return set(resp.json().keys())
    except:
        pass
    return set() # Fallback

### user endpoints
# user get
@app.get("/users/me", response_model=UsersResponse, tags=["Users"], summary="Get the currently logged-in user")
async def get_user(current_user: UserDB = Depends(get_current_user)):
    return current_user


### model endpoints
# get a particular model
@app.get("/models/{model_id}", response_model=ModelResponse, tags=["Models"], summary="Get a model summary by ID")
async def get_model(model_id: uuid.UUID, session: Session = Depends(get_session)):
    model_fetch = session.get(MLModelDB, model_id)
    if not model_fetch:
        raise HTTPException(status_code=404, detail="Model not found")
    return ModelResponse(**model_fetch.model_dump(),
        author_username=model_fetch.author.username)

# get all models
@app.get("/models", response_model=List[ModelResponse], tags=["Models"], summary="Get all model summaries")
async def get_all_models(author_id: uuid.UUID | None = None,
                         session: Session = Depends(get_session)):
    statement = select(MLModelDB)
    if author_id:
        statement = statement.where(MLModelDB.author_id == author_id)
    models = session.exec(statement).all()
    return models

# model post
@app.post("/models/{model_id}", response_model=ModelResponse, tags=["Models"], summary="Create a new model")
async def create_model(model_id: uuid.UUID,
                       model_data: ModelCreate,
                       current_user: UserDB = Depends(get_current_user),
                       session: Session = Depends(get_session)):
    model_fetch = session.get(MLModelDB, model_id)
    if model_fetch:
        raise HTTPException(status_code=409, detail="Model already exists")
    # check if model task is a valid HF task, and warn if not
    valid_tasks = get_valid_hf_tasks()
    if model_data.task not in valid_tasks:
        # Soft Warning
        print(f"Warning: Unknown task '{model_data.task}'. Accepted anyway.")

    # add model_id to model_data
    model_data.id = model_id
    session.add(model_data)
    try:
        session.commit()
    # throw a helpful conflict error if you try to write a value that already exists for a unique field
    except sqlalchemy.exc.IntegrityError as e:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    session.refresh(model_data)
    return model_data

# model update
@app.patch("/models/{model_id}", response_model=ModelResponse, tags=["Models"], summary="Update a model via patch")
async def update_model(model_id: uuid.UUID,
                       model_data: ModelUpdate,
                       current_user: UserDB = Depends(get_current_user),
                       session: Session = Depends(get_session)):
    # check if model exists
    model_fetch = session.get(MLModelDB, model_id)
    if not model_fetch:
        raise HTTPException(status_code=404, detail="Model not found")
    # update model data
    model_data = model_data.model_dump(exclude_unset=True)
    
    for key, value in model_data.items():
        setattr(model_fetch, key, value)

    session.add(model_fetch)
    try:
        session.commit()
    # throw a helpful conflict error if you try to write a value that already exists for a unique field
    except sqlalchemy.exc.IntegrityError as e:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    session.refresh(model_fetch)
    return model_fetch

### model version endpoints
# get a particular model version
@app.get("/models/{model_id}/versions/{version_id}", response_model=ModelVerResponse, tags=["Model Versions"], summary="Get a model version summary by ID")
async def get_model_version(model_id: uuid.UUID, 
                            version_id: uuid.UUID,
                            session: Session = Depends(get_session)):
    # check if model version even exists
    statement = select(ModelVersionDB).where(
        ModelVersionDB.model_id == model_id,
        ModelVersionDB.id == version_id
    )
    model_ver = session.exec(statement).one()
    if not model_ver:
        raise HTTPException(status_code=404, detail="Model version not found")
    # return model version data
    return model_ver

# get all of a model's versions
@app.get("/models/{model_id}/versions", response_model=List[ModelVerResponse], tags=["Model Versions"], summary="Get all model version summaries")
async def get_all_versions(model_id: uuid.UUID,
                           session: Session = Depends(get_session)):
    statement = select(ModelVersionDB).where(ModelVersionDB.model_id == model_id)
    model_versions = session.exec(statement).all()
    return model_versions

# model version post
@app.post("/models/{model_id}/versions/{version_id}", response_model=ModelVerResponse, tags=["Model Versions"], summary="Create a new model version")
async def create_model_version(model_id: uuid.UUID,
                               version_id: uuid.UUID,
                               model_ver_data: ModelVersionDB,
                               current_user: UserDB = Depends(get_current_user),
                               session: Session = Depends(get_session)):
    # check if model version already exists
    statement = select(ModelVersionDB).where(
        ModelVersionDB.model_id == model_id,
        ModelVersionDB.id == version_id
    )
    model_ver = session.exec(statement).all()
    if model_ver:
        raise HTTPException(status_code=409, detail="Model version already exists")
    model_ver_data.model_id = model_id
    model_ver_data.id = version_id
    session.add(model_ver_data)
    try:
        session.commit()
    # throw a helpful conflict error if you try to write a value that already exists for a unique field
    except sqlalchemy.exc.IntegrityError as e:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    session.refresh(model_ver_data)
    return model_ver_data

# model version update
@app.patch("/models/{model_id}/versions/{version_id}", response_model=ModelVerResponse, tags=["Model Versions"], summary="Update a model version via patch")
async def update_model_version(model_id: uuid.UUID,
                               version_id: uuid.UUID,
                               model_ver_data: ModelVerUpdate,
                               current_user: UserDB = Depends(get_current_user),
                               session: Session = Depends(get_session)):
    # check if model version already exists
    statement = select(ModelVersionDB).where(
        ModelVersionDB.model_id == model_id,
        ModelVersionDB.id == version_id
    )
    model_ver = session.exec(statement).one()
    if not model_ver:
        raise HTTPException(status_code=409, detail="Model version doesn't exist")
    update_data = model_ver_data.model_dump(exclude_unset=True)
    
    for key, value in update_data.items():
        setattr(model_ver, key, value)

    session.add(model_ver)
    try:
        session.commit()
    # throw a helpful conflict error if you try to write a value that already exists for a unique field
    except sqlalchemy.exc.IntegrityError as e:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    session.refresh(model_ver)
    return model_ver

# Search HF for models with TFLite files
class HFSearchResult(BaseModel):
    id: str
    description: str
    tags: List[str]
    pipeline_tag: Optional[str] = None

class HFSearchResponse(BaseModel):
    results: List[HFSearchResult]

@app.get("/search/huggingface", response_model=HFSearchResponse, tags=["Hugging Face"], summary="Search Hugging Face for TFLite models")
def search_huggingface(query: str, 
                       ):
    """
    Search Hugging Face for models that contain .tflite files.
    Filters to only return models with actual TFLite files.
    """
    if not query or len(query.strip()) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")
    
    try:
        # Use HF token if available from environment
        hf_token = os.getenv("HUGGINGFACE_TOKEN")
        if hf_token:
            api = HfApi(token=hf_token) 
            print("Searching HuggingFace using token")
        else:
            api = HfApi()
            print("Searching HuggingFace without token")
        
        # Search HF for models without framework filter to avoid auth issues
        # The pytorch filter was too restrictive and causing rate limit issues
        hf_models = api.list_models(
            search=query,
            limit=30,
            full=False  # Don't fetch full metadata for initial search
        )
        
        results = []
        
        # Filter to only models with .tflite files
        for model_info in hf_models:
            try:
                # Get detailed info with file listing
                detailed_info = api.model_info(repo_id=model_info.id, files_metadata=True)
                
                # Check if it has tflite files
                if detailed_info.siblings is None:
                    continue
                    
                tflite_files = [f for f in detailed_info.siblings if f.rfilename.endswith(".tflite")]
                
                if tflite_files:  # Only include if it has TFLite files
                    # Safely extract description
                    description = ""
                    if detailed_info.cardData and isinstance(detailed_info.cardData, dict):
                        description = detailed_info.cardData.get("summary", "") or detailed_info.cardData.get("description", "")
                    
                    results.append(HFSearchResult(
                        id=model_info.id,
                        description=description if description else "TFLite model from Hugging Face",
                        tags=detailed_info.tags or [],
                        pipeline_tag=detailed_info.pipeline_tag
                    ))
                    
                    # Limit results to avoid too many API calls
                    if len(results) >= 15:
                        break
                        
            except Exception as e:
                # Log but skip models that fail to load details
                # Common issues: private models, API timeouts, etc.
                continue
        
        return HFSearchResponse(results=results)
        
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=503, detail="Unable to connect to Hugging Face. Please check your internet connection and try again.")
    except Exception as e:
        error_msg = str(e)
        # Be more specific about common errors
        if "401" in error_msg or "Unauthorized" in error_msg:
            raise HTTPException(status_code=401, detail="Hugging Face API error: Please check if the HF token is valid or if you've hit the rate limit. Try again later.")
        elif "rate" in error_msg.lower():
            raise HTTPException(status_code=429, detail="Hugging Face rate limit reached. Please wait a moment and try again.")
        else:
            raise HTTPException(status_code=500, detail=f"Failed to search Hugging Face: {error_msg[:100]}")

# create a model from HF
@app.post("/import/huggingface", response_model=ModelResponse, tags=["Hugging Face"], summary="Import a model directly from Hugging Face")
def import_from_huggingface(
    payload: HFImportRequest,
    user: UserDB = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    api = HfApi()
    
    # 1. Fetch Model Info from HF
    try:
        model_info = api.model_info(repo_id=payload.hf_id, files_metadata=True)
    except Exception:
        raise HTTPException(status_code=404, detail="Hugging Face repo not found")

    # 2. FILTER: Ensure it is a TFLite model
    tflite_files = [f for f in model_info.siblings if f.rfilename.endswith(".tflite")]
    
    if not tflite_files:
        raise HTTPException(status_code=400, detail="No .tflite files found in this repo")

    # 3. Create the Parent Model (Mapping Logic)
    # Map HF tags to our tags
    hf_tags = model_info.tags or []
    #our_tags = [t for t in hf_tags if t in ["vision", "audio", "text"]] # Simple filter
    
    # Map License (data schema uses HF's license strings directly)
    license_str = model_info.cardData.get("license", "unknown")
    license_enum = LicenseType(license_str) if license_str in LicenseType.__members__ else LicenseType.UNKNOWN
    
    new_model = MLModelDB(
        name=payload.hf_id.title(), # "mobilenet-v2"
        slug=payload.hf_id.replace("/", "-"),
        description=f"Imported from Hugging Face: {payload.hf_id}",
        category=ModelCategory.OTHER, # You might want to guess this based on tags
        license_type=license_enum,
        origin_repo_url=f"https://huggingface.co/{payload.hf_id}",
        hf_model_id=payload.hf_id, # <--- STORE THE ID
        author_id=user.id,
        tags=hf_tags,
        task=model_info.pipeline_tag
    )
    
    session.add(new_model)
    # session.flush() # Generate ID

    # # 4. Create the Version (Asset Mapping)
    # # We take the first TFLite file found (or you could loop through them)
    # primary_file = tflite_files[0]
    
    # # Generate the direct download URL (CDN)
    # download_url = hf_hub_url(
    #     repo_id=payload.hf_id, 
    #     filename=primary_file.rfilename, 
    #     revision=model_info.sha
    # )

    # assets = [
    #     MLModelAsset(
    #         asset_key="model_file",
    #         asset_type=AssetType.TFLite,
    #         source_url=download_url, # Direct link to HF CDN
    #         file_size_bytes=0, # HF API usually provides this in 'lfs' metadata, requires deeper check
    #         file_hash=model_info.sha, # Use commit SHA as proxy for hash initially
    #         is_hosted_by_us=False # Important!
    #     )
    # ]

    # new_version = ModelVersionDB(
    #     model_id=new_model.id,
    #     version_string="1.0.0",
    #     hf_commit_sha=model_info.sha, # <--- STORE THE SHA
    #     pipeline_spec=PipelineConfig(input_nodes=[], output_nodes=[]), # Empty placeholder
    #     assets=[a.dict() for a in assets],
    #     published_at=datetime.now(UTC)
    # )

    # session.add(new_version)
    # session.commit()
    session.refresh(new_model)
    
    return new_model


# ==========================================
# HUGGINGFACE LITERT SYNC ENDPOINT
# ==========================================
class SyncResponse(BaseModel):
    status: str
    created: int
    updated: int
    skipped: int
    message: str

@app.post("/sync/huggingface/litert", response_model=SyncResponse, tags=["Hugging Face"], summary="Manually trigger HuggingFace LiteRT model sync")
def manual_sync_literrt_models(current_user: UserDB = Depends(get_current_user)):
    """
    Manually trigger the HuggingFace LiteRT model sync job.
    This endpoint is protected - only authenticated users can trigger it.
    Useful for testing or force-syncing models outside the scheduled time.
    """
    # In production, you might want to restrict this to admin users
    try:
        logger.info(f"Manual sync triggered by user: {current_user.username}")
        stats = run_sync(limit=settings.HF_SYNC_FETCH_LIMIT)
        
        return SyncResponse(
            status="success",
            created=stats.get("created", 0),
            updated=stats.get("updated", 0),
            skipped=stats.get("skipped", 0),
            message=f"Successfully synced LiteRT models. Created: {stats.get('created', 0)}, Updated: {stats.get('updated', 0)}, Skipped: {stats.get('skipped', 0)}"
        )
    except Exception as e:
        logger.error(f"Error during manual sync: {e}")
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")
