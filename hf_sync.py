"""
HuggingFace LiteRT Model Syncer

This module fetches all public models with "LiteRT" library from HuggingFace
and creates/updates corresponding model objects in Pocket AI database.

This script is designed to run daily via APScheduler.
"""

import logging
from typing import List, Dict, Any, Optional
import uuid
from datetime import datetime, timezone
from sqlmodel import Session, select
from huggingface_hub import HfApi
import sqlalchemy
import urllib.error

from schema import MLModelDB, UserDB, ModelCategory, LicenseType
from database import engine
from config import get_settings

# get .env configs
settings = get_settings()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_or_create_system_user(session: Session) -> UserDB:
    """
    Get or create a system user for synced models.
    All auto-synced models will be attributed to this user.
    """
    statement = select(UserDB).where(UserDB.username == "hf_sync_system")
    system_user = session.exec(statement).first()
    
    if not system_user:
        system_user = UserDB(
            id=uuid.uuid4(),
            username="hf_sync_system",
            email="system@pocket-ai.local",
            is_developer=True,
            hf_username=None
        )
        session.add(system_user)
        session.commit()
        session.refresh(system_user)
        logger.info(f"Created system user: {system_user.id}")
    
    return system_user


def fetch_literrt_models(limit: int = settings.HF_SYNC_FETCH_LIMIT) -> List[Dict[str, Any]]:
    """
    Fetch all public HuggingFace models with 'LiteRT' library.
    
    Returns a list of model info dictionaries.
    """
    api = HfApi()
    models = []
    
    try:
        logger.info("Starting fetch of LiteRT models from HuggingFace...")
        
        # Query for models with LiteRT library using the filter parameter
        # This is more efficient than search
        result = api.list_models(
            filter="tflite",
            limit=limit,
            full=True,  # Get full metadata
        )
        
        public_count = 0
        private_count = 0

        for model_info in result:
            # Filter to only public models
            if model_info.private:
                private_count += 1
                continue
            
            # Filter to only applicable mobile-optimized models, using library or tag names
            #if (model_info.library_name in settings.HF_APPLICABLE_LIBRARIES) or (any(lib in model_info.tags for lib in settings.HF_APPLICABLE_LIBRARIES)):
            # Extract description safely
            description = ""
            if model_info.cardData and isinstance(model_info.cardData, dict):
                description = model_info.cardData.get("summary", "") or model_info.cardData.get("description", "")
            
            models.append({
                "id": model_info.id,
                "name": model_info.id.split("/")[-1],  # Use repo name
                "description": description,
                "tags": model_info.tags or [],
                "task": model_info.pipeline_tag,
                "license": model_info.cardData.get("license", "unknown") if model_info.cardData else "unknown",
                "sha": model_info.sha,
            })

            public_count += 1
            
           # else:
           #     logger.debug(f"Skipping model {model_info.id} - library '{model_info.library_name}' not in applicable list.")
        
        logger.info(f"Found {public_count} public LiteRT models after filtering, and {private_count} private models. Ready for syncing.")
        return models
        
    except urllib.error.HTTPError as e:
        logger.error(f"HuggingFace API error: {e}")
        raise
    except Exception as e:
        logger.error(f"Error fetching models: {e}")
        raise


def map_hf_license_to_enum(license_str: str) -> str:
    """Map HuggingFace license string to our LicenseType enum."""
    if not license_str:
        return LicenseType.UNKNOWN
    
    # Normalize the string
    license_str = license_str.lower().strip()
    
    # Try direct mapping
    for license_type in LicenseType:
        if license_type.value == license_str:
            return license_type
    
    # Fallback to UNKNOWN if no match
    return LicenseType.UNKNOWN


def sync_literrt_models(models: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Sync fetched LiteRT models to the database.
    
    Returns a dict with counts:
    - created: number of new models created
    - updated: number of existing models updated
    - skipped: number of models skipped due to errors
    """
    with Session(engine) as session:
        system_user = get_or_create_system_user(session)
        stats = {"created": 0, "updated": 0, "skipped": 0}
        
        for model_data in models:
            try:
                hf_model_id = model_data["id"]
                
                # Check if model already exists
                statement = select(MLModelDB).where(
                    MLModelDB.hf_model_id == hf_model_id
                )
                existing_model = session.exec(statement).first()
                
                if existing_model:
                    # Update existing model with new metadata
                    existing_model.tags = model_data["tags"]
                    existing_model.task = model_data["task"]
                    existing_model.description = model_data["description"]
                    session.add(existing_model)
                    stats["updated"] += 1
                    logger.debug(f"Updated model: {hf_model_id}")
                    
                else:
                    # Create new model
                    new_model = MLModelDB(
                        id=uuid.uuid4(),
                        name=model_data["name"],
                        slug=hf_model_id.lower().replace("/", "-"),
                        description=model_data["description"] or f"LiteRT model from HuggingFace: {hf_model_id}",
                        category=ModelCategory.UTILITY,  # Default category
                        license_type=map_hf_license_to_enum(model_data["license"]),
                        origin_repo_url=f"https://huggingface.co/{hf_model_id}",
                        hf_model_id=hf_model_id,
                        author_id=system_user.id,
                        tags=model_data["tags"],
                        task=model_data["task"],
                        is_verified_official=False,
                        total_download_count=0,
                        rating_weighted_avg=0.0,
                        total_ratings=0,
                    )
                    session.add(new_model)
                    stats["created"] += 1
                    logger.debug(f"Created new model: {hf_model_id}")
                    
            except sqlalchemy.exc.IntegrityError as e:
                session.rollback()
                logger.warning(f"Integrity error for {model_data['id']}: {e}")
                stats["skipped"] += 1
                
            except Exception as e:
                session.rollback()
                logger.error(f"Error syncing model {model_data['id']}: {e}")
                stats["skipped"] += 1
        
        # Commit all changes
        try:
            session.commit()
            logger.info(f"Sync completed - Created: {stats['created']}, Updated: {stats['updated']}, Skipped: {stats['skipped']}")
        except Exception as e:
            session.rollback()
            logger.error(f"Error committing transaction: {e}")
            raise
        
        return stats


def run_sync(limit: int = settings.HF_SYNC_FETCH_LIMIT) -> Dict[str, int]:
    """
    Main entry point for the HuggingFace sync job.
    Fetches LiteRT models and syncs them to the database.
    """
    try:
        logger.info("=" * 60)
        logger.info("Starting HuggingFace LiteRT Model Sync")
        logger.info("=" * 60)
        
        # Fetch models from HuggingFace
        models = fetch_literrt_models(limit=limit)  # Adjust limit as needed
        
        # Sync to database
        stats = sync_literrt_models(models)
        
        logger.info("=" * 60)
        logger.info("HuggingFace LiteRT Model Sync Completed Successfully")
        logger.info(f"Results: {stats}")
        logger.info("=" * 60)
        
        return stats
        
    except Exception as e:
        logger.error(f"Fatal error during sync: {e}")
        raise


if __name__ == "__main__":
    # Run the sync manually for testing
    run_sync()
