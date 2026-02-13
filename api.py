from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from enum import Enum
from typing import List, Dict, Any, Optional
import uuid
from datetime import datetime, UTC
from fastapi.middleware.cors import CORSMiddleware
import sqlalchemy

from schema import ModelCategory, AssetType, DevicePlatform, LicenseType, PipelineConfig, MLModelAsset, MLModelDB, UserDB, ModelVersionDB
from database import engine, get_session
from sqlmodel import Field, Session, SQLModel, create_engine, select
from auth import get_current_user


# user DTOs
# user get
class UsersResponse(BaseModel):
    id: uuid.UUID
    username: str
    email: str
    is_developer: bool
    created_at: datetime

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
class ModelResponse(BaseModel):
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
class ModelCreate(BaseModel):
    name: str
    slug: Optional[str] = None
    description: str | None = None
    category: ModelCategory
    tags: Optional[List[str]] = None

# model put
class ModelUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str | None] = None
    category: Optional[ModelCategory] = None
    tags: Optional[List[str]] = None
    total_download_count: Optional[int] = None

# model version DTOs
# model version get
class ModelVerResponse(BaseModel):
    id: uuid.UUID
    version_string: str
    changelog: Optional[str]
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
class ModelVerCreate(BaseModel):
    id: uuid.UUID
    model_id: uuid.UUID
    pipeline_spec: PipelineConfig
    assets: List[MLModelAsset]

# model version put
class ModelVerUpdate(BaseModel):
    id: uuid.UUID
    model_id: uuid.UUID
    pipeline_spec: Optional[PipelineConfig] = None
    assets: Optional[List[MLModelAsset]] = None
    download_count: Optional[int] = None
    num_ratings: Optional[int] = None
    rating_avg: Optional[float] = None


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
    ]
)

# CORS
origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

