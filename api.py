from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from enum import Enum
from typing import List, Dict, Any, Optional
import uuid
from datetime import datetime, UTC

from schema import ModelCategory, AssetType, DevicePlatform, LicenseType, PipelineConfig, MLModelAsset, MLModelDB, UserDB
from database import engine, get_session
from sqlmodel import Field, Session, SQLModel, create_engine, select


# user DTOs
# user get
class UsersResponse(BaseModel):
    id: uuid.UUID
    username: str
    email: str

    class Config:
        from_attributes = True

# user post
class UsersCreate(BaseModel):
    username: str
    email: str

# user put
class UsersUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None

# model DTOs
# model get
class ModelsResponse(BaseModel):
    name: str
    slug: Optional[str] = None
    description: str | None
    category: ModelCategory
    id: uuid.UUID
    author_id: uuid.UUID
    tags: List[str]
    total_download_count: int
    rating_weighted_avg: float
    total_ratings: int
    created_at: datetime

# model post
class ModelsCreate(BaseModel):
    name: str
    slug: Optional[str] = None
    description: str | None = None
    category: ModelCategory
    tags: Optional[List[str]] = None

# model put
class ModelsUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str | None] = None
    category: Optional[ModelCategory] = None
    tags: Optional[List[str]] = None
    total_download_count: Optional[int] = None

# model version DTOs
# model version get
class ModelsVerResponse(BaseModel):
    version_string: str
    changelog: Optional[str]
    id: uuid.UUID
    model_id: uuid.UUID
    
    # COMPLEX JSONB COLUMNS
    pipeline_spec: PipelineConfig
    assets: List[MLModelAsset]
    
    # Telemetry Aggregates
    published_at: datetime
    download_count: int
    num_ratings: int
    rating_avg: float

# model version post
class ModelsVerCreate(BaseModel):
    model_id: uuid.UUID
    pipeline_spec: PipelineConfig
    assets: List[MLModelAsset]

# model version put
class ModelsVerUpdate(BaseModel):
    pipeline_spec: Optional[PipelineConfig] = None
    assets: Optional[List[MLModelAsset]] = None
    download_count: Optional[int] = None
    num_ratings: Optional[int] = None
    rating_avg: Optional[float] = None


app = FastAPI()

### user endpoints
# user get
@app.get("/users/{user_id}", response_model=UsersResponse)
async def get_user(user_id: uuid.UUID, session: Session = Depends(get_session)):
    user_fetch = session.get(UserDB, user_id)
    if not user_fetch:
        raise HTTPException(status_code=404, detail="User not found")
    return user_fetch


### model endpoints
# model get
@app.get("/models/{model_id}", response_model=ModelsResponse)
async def get_model(model_id: uuid.UUID, session: Session = Depends(get_session)):
    model_fetch = session.get(MLModelDB, model_id)
    if not model_fetch:
        raise HTTPException(status_code=404, detail="Model not found")
    return ModelsResponse(**model_fetch.model_dump(),
        author_username=model_fetch.author.username)

# model post
@app.post("/models")
async def create_model(model_data: ModelsCreate):
    pass