# HuggingFace LiteRT Model Sync System

## Overview

This system automatically syncs all public LiteRT models from HuggingFace to Pocket AI on a daily basis. Instead of requiring users to manually search for and upload models, all ~763 LiteRT models from HuggingFace are automatically available in the Pocket AI application.

## Features

- **Automatic Daily Sync**: Runs daily at 2:00 AM UTC
- **Incremental Updates**: Only creates new models, updates metadata for existing ones
- **Error Resilient**: Skips models with errors and continues processing
- **Manual Trigger**: Can be triggered manually via API endpoint
- **System User Attribution**: All synced models are attributed to a "hf_sync_system" user
- **Logging**: Comprehensive logging for monitoring and debugging

## Files

### New Files

1. **`hf_sync.py`** - Core sync logic
   - `fetch_literrt_models()` - Queries HuggingFace for LiteRT models
   - `sync_literrt_models()` - Syncs models to the database
   - `run_sync()` - Main entry point

2. **`requirements.txt`** - Python dependencies including APScheduler

### Modified Files

**`api.py`** - Added:
   - Scheduler initialization with APScheduler
   - Startup/shutdown event handlers
   - Manual sync endpoint: `POST /sync/huggingface/litert`

## Installation

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

Key new dependency:
- `APScheduler==3.10.4` - For background job scheduling

### 2. Start the API

The sync job is automatically started when the FastAPI server starts:

```bash
fastapi dev api.py
# or
uvicorn api:app --reload
```

## Usage

### Automatic Sync (Daily)

The sync runs automatically every day at **2:00 AM UTC**. You can monitor the logs to see when it runs:

```
INFO:hf_sync:============================================================
INFO:hf_sync:Starting HuggingFace LiteRT Model Sync
INFO:hf_sync:============================================================
INFO:hf_sync:Starting fetch of LiteRT models from HuggingFace...
INFO:hf_sync:Fetched 763 LiteRT models from HuggingFace
INFO:hf_sync:Sync completed - Created: 150, Updated: 20, Skipped: 2
INFO:hf_sync:============================================================
INFO:hf_sync:HuggingFace LiteRT Model Sync Completed Successfully
```

### Manual Sync (Testing/Admin)

Trigger a manual sync at any time via the API endpoint:

```bash
curl -X POST http://localhost:8000/sync/huggingface/litert \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"
```

Response:
```json
{
  "status": "success",
  "created": 150,
  "updated": 20,
  "skipped": 2,
  "message": "Successfully synced LiteRT models. Created: 150, Updated: 20, Skipped: 2"
}
```

## How It Works

### 1. Model Discovery
- Queries HuggingFace API with `filter="LiteRT"`
- Fetches up to 500 public models (configurable in `run_sync()`)
- Extracts model metadata: name, description, tags, task, license

### 2. Database Sync
For each model:
- Checks if model already exists by `hf_model_id`
- **New Model**: Creates a new `MLModelDB` entry with:
  - HuggingFace ID stored in `hf_model_id`
  - Metadata from HF (description, tags, task, license)
  - Default category as `UTILITY`
  - No versions (users create these manually)
  - Attributed to "hf_sync_system" user
  
- **Existing Model**: Updates metadata (tags, task, description)

### 3. Error Handling
- Integrity errors (duplicate slugs, etc.) are logged and skipped
- Failed models don't block the sync
- Transaction rollback on errors maintains database consistency

## System User

All synced models are attributed to the `hf_sync_system` user:
- Username: `hf_sync_system`
- Email: `system@pocket-ai.local`
- Role: Developer (is_developer=true)
- Created automatically on first sync

## Configuration

### Change Sync Schedule

Edit the scheduler in `api.py`:

```python
scheduler.add_job(
    run_sync,
    CronTrigger(hour=2, minute=0),  # Change this to your preferred time
    id='hf_litert_sync',
    ...
)
```

Common schedule examples:
- **Daily at 1 AM UTC**: `CronTrigger(hour=1, minute=0)`
- **Every 6 hours**: `CronTrigger(hour='*/6', minute=0)`
- **Weekly on Monday at 2 AM**: `CronTrigger(day_of_week='mon', hour=2, minute=0)`

### Change Model Limit

Edit the limit in `hf_sync.py`:

```python
def run_sync() -> Dict[str, int]:
    models = fetch_literrt_models(limit=1000)  # Change from 500
```

### Force Sync on Startup

Toggle sync on app startup:

```python
# In api.py startup event:
# scheduler.add_job(..., name='HuggingFace LiteRT Model Sync')
# To skip startup sync, comment out or remove the add_job call
```

## Monitoring & Debugging

### View Scheduler Status

Check if the scheduler is running (add this endpoint if needed):

```python
@app.get("/admin/scheduler/status")
def get_scheduler_status():
    jobs = scheduler.get_jobs()
    return {
        "running": scheduler.running,
        "jobs": [
            {
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time,
            }
            for job in jobs
        ]
    }
```

### Check Logs

Monitor the application logs for sync activity:

```bash
# On Windows with PowerShell
Get-Content logs.txt -Tail 50  # View last 50 lines
```

### Database Query

Check which models were synced:

```sql
SELECT id, name, hf_model_id, created_at, author_id 
FROM ml_models 
WHERE hf_model_id IS NOT NULL 
ORDER BY created_at DESC 
LIMIT 20;
```

## Future Enhancements

1. **Version Auto-Pull**: Automatically create model versions from HF
2. **Metadata Sync**: Periodically update model metadata (downloads, ratings)
3. **Deletion Handling**: Remove models that are no longer public on HF
4. **Filtering Rules**: More sophisticated model selection (by framework, size, etc.)
5. **Notification System**: Alert admins when sync fails
6. **Rate Limit Handling**: Implement exponential backoff for HF API limits

## Troubleshooting

### Issue: Scheduler Not Running
- Check logs for startup errors
- Verify APScheduler is installed: `pip list | grep APScheduler`
- Ensure database connection is valid

### Issue: Models Not Appearing
- Check if sync ran: look for log messages
- Verify database connection
- Check `ml_models` table for entries with `hf_model_id` not null

### Issue: HuggingFace API Errors
- Check internet connection
- Verify HF API is accessible: `curl https://huggingface.co/api/models`
- Check HF rate limits - sync will retry with backoff

### Issue: Duplicate Models
- The system checks `hf_model_id` uniqueness before creating
- If duplicates exist, they'll be skipped

## API Integration

The sync system integrates seamlessly with existing endpoints:

- **GET /models** - Lists all models including synced LiteRT models
- **GET /models/{id}** - View synced model details
- **GET /models/{id}/versions** - Empty for auto-synced models (users add versions)
- **POST /sync/huggingface/litert** - Manually trigger sync

Users cannot edit auto-synced models' metadata through normal endpoints, but can create versions for them.
