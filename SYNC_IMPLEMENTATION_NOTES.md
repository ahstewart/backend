# HuggingFace LiteRT Automatic Sync - Implementation Summary

## What Changed

Your Pocket AI system now has an **automated daily sync** that discovers and creates model objects for all ~763 public LiteRT models from HuggingFace. This eliminates the need for manual ad-hoc uploads of individual models.

## What This Means

### Before
- Users had to manually search HuggingFace for LiteRT models
- Users uploaded models one at a time through the web interface
- No guarantee all available models were in the system

### After
- All public LiteRT models from HuggingFace are automatically available
- New models appear daily (after 2 AM UTC)
- Users can immediately create versions for any model
- No manual upload needed for HF models

## What Got Added

### 1. New Files
- **`hf_sync.py`** (227 lines) - Core sync logic
- **`requirements.txt`** - Dependencies including APScheduler
- **`HF_SYNC_GUIDE.md`** - Comprehensive documentation

### 2. Modified Files
- **`api.py`** - Added scheduler setup and manual sync endpoint

### 3. New Database User
- **`hf_sync_system`** - System user that owns all auto-synced models
- Created automatically on first sync

## Installation Steps

### Step 1: Install Dependencies
```bash
cd model-service\backend
pip install -r requirements.txt
```

### Step 2: Restart Your API
The scheduler starts automatically when FastAPI boots:

```bash
# Windows PowerShell
python -m uvicorn api:app --reload

# Or using FastAPI CLI
fastapi dev api.py
```

### Step 3: Verify It's Running
Check the logs for:
```
INFO:root:Background scheduler started - HF LiteRT sync scheduled for 02:00 UTC daily
```

### Step 4: (Optional) Test Manual Sync
Trigger a sync immediately to verify it works:

```bash
# Use any tool to POST to the endpoint (you need a valid JWT token)
curl -X POST http://localhost:8000/sync/huggingface/litert \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"
```

Response example:
```json
{
  "status": "success",
  "created": 150,
  "updated": 20,
  "skipped": 2,
  "message": "Successfully synced LiteRT models. Created: 150, Updated: 20, Skipped: 2"
}
```

## Architecture Changes

### Data Flow

```
┌─────────────────────┐
│  HuggingFace API    │  (LiteRT models)
└──────────┬──────────┘
           │
           ▼
    ┌──────────────────┐
    │   hf_sync.py     │  (Filter, map, sync)
    └──────────┬───────┘
               │
               ▼
    ┌──────────────────────┐
    │  PostgreSQL Database │  (ml_models table)
    └──────────────────────┘
               ▲
               │
    ┌──────────┴────────┐
    │   Scheduler       │  (Runs daily at 2 AM UTC)
    │  (APScheduler)    │
    └───────────────────┘
```

### Model Object Structure

Every synced model has:

```
MLModelDB
├── id: uuid (auto-generated)
├── name: str (from HF)
├── slug: str (derived from HF ID)
├── description: str (from HF metadata)
├── category: "utility" (default)
├── hf_model_id: str (e.g. "google/mobilenet_v1")
├── tags: list (from HF)
├── task: str (e.g. "image-classification")
├── license_type: enum (mapped from HF)
├── author_id: uuid (points to hf_sync_system)
├── versions: [] (empty - users create these)
└── origin_repo_url: str (link to HF)
```

## Key Properties

### 1. **No Versions Created**
- Models are created without versions
- Users manually create versions later
- This allows flexibility in versioning strategy

### 2. **Daily Schedule**
- Runs every day at **2:00 AM UTC**
- Can be changed in `api.py` scheduler config
- Configurable frequency (hourly, weekly, etc.)

### 3. **Incremental Updates**
- Only creates NEW models
- Updates metadata for EXISTING models
- Efficient - skips what's already there

### 4. **Error Resilience**
- Skips models that fail
- Continues with next model
- Detailed logging of all failures

### 5. **Manual Trigger Available**
- Endpoint: `POST /sync/huggingface/litert`
- Useful for testing or urgent syncs
- Requires authentication (any logged-in user)

## System Requirements

### Python Packages
All added to `requirements.txt`:
- `APScheduler==3.10.4` - Background scheduling
- Everything else was already listed

### Database
- No schema changes
- Existing `ml_models` table used
- Indexes already present

### Network
- Needs internet access to HuggingFace API
- Most HF queries are public (no token needed)
- Rate limits: HF allows ~1000 requests/hour

## Impact on Users

### Web App Users
- **Browse Models**: ~763 more models available automatically
- **Create Versions**: Can now create versions for auto-synced models
- **No Manual Upload**: Don't need to search/upload HF models anymore

### Admin/API Users
- **Model Management**: Can view all synced models via API
- **Monitoring**: Can trigger manual sync via endpoint
- **Logging**: Complete audit trail of all syncs

### Developers
- **Consistent Attribution**: All synced models linked to `hf_sync_system`
- **HF IDs Tracked**: `hf_model_id` field stores original HF repo ID
- **Origin URL**: `origin_repo_url` links back to HF

## Configurations

### Change Sync Time

In `api.py`, modify the `CronTrigger`:

```python
# Current: 2 AM UTC
CronTrigger(hour=2, minute=0)

# Examples:
CronTrigger(hour=0, minute=0)           # Midnight UTC
CronTrigger(hour='*/6', minute=0)       # Every 6 hours
CronTrigger(day_of_week='mon', hour=2)  # Weekly, Monday 2 AM
```

### Change Model Limit

In `hf_sync.py`, modify the fetch limit:

```python
def run_sync() -> Dict[str, int]:
    models = fetch_literrt_models(limit=1000)  # Default was 500
```

### Disable Auto-Sync

Comment out the `scheduler.add_job()` call in `api.py` startup event. Manual sync will still be available via endpoint.

## Monitoring

### Check Sync Status
```sql
-- Count of synced models
SELECT COUNT(*) FROM ml_models 
WHERE hf_model_id IS NOT NULL;

-- Recently synced models
SELECT name, hf_model_id, created_at FROM ml_models 
WHERE hf_model_id IS NOT NULL 
ORDER BY created_at DESC LIMIT 10;

-- System user
SELECT * FROM users WHERE username = 'hf_sync_system';
```

### View Logs
The logger outputs to console with prefix `hf_sync`. Example:
```
INFO:hf_sync:Starting fetch of LiteRT models from HuggingFace...
INFO:hf_sync:Fetched 763 LiteRT models from HuggingFace
INFO:hf_sync:Sync completed - Created: 150, Updated: 20, Skipped: 2
```

## Potential Issues & Solutions

### Issue: Scheduler Not Starting
**Solution**: Check that APScheduler is installed
```bash
pip list | grep APScheduler
# Should show: APScheduler 3.10.4
```

### Issue: Models Not Appearing
**Solution**: Check database and logs
```sql
SELECT COUNT(*) FROM ml_models WHERE hf_model_id IS NOT NULL;
```
Look for errors in logs mentioning `hf_sync`.

### Issue: Duplicate Models
**Solution**: This shouldn't happen - the system checks `hf_model_id` uniqueness

### Issue: HF API Rate Limit
**Solution**: System will retry or skip. Check logs for details. Unlikely with 500 model limit.

## Next Steps

1. ✅ Install dependencies: `pip install -r requirements.txt`
2. ✅ Restart API server
3. ✅ Verify scheduler is running (check logs)
4. ✅ Test manual sync endpoint
5. ✅ Wait for daily sync (or trigger manually)
6. ✅ Check that models appear in `/models` endpoint
7. ✅ Test creating a version for a synced model
8. ✅ Monitor logs for any issues

## Questions or Issues?

Check the detailed guide: `HF_SYNC_GUIDE.md`
