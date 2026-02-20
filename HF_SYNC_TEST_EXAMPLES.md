# Testing & Examples Guide

## Testing the Sync System

### Method 1: Trigger Manual Sync via API

**Prerequisite:** You need a valid JWT token. Get one by logging in first.

```bash
# Example using curl
curl -X POST http://localhost:8000/sync/huggingface/litert \
  -H "Authorization: Bearer eyJhbG..." \
  -H "Content-Type: application/json"
```

**Response (Success):**
```json
{
  "status": "success",
  "created": 150,
  "updated": 5,
  "skipped": 2,
  "message": "Successfully synced LiteRT models. Created: 150, Updated: 5, Skipped: 2"
}
```

**Response (Error):**
```json
{
  "detail": "Sync failed: Connection to HuggingFace API failed"
}
```

### Method 2: Check Logs

Watch the application logs while the sync runs:

```bash
# PowerShell: watch logs in real-time if output to console
# Otherwise check your log file
Get-Content logs.txt -Tail 20 -Wait
```

Expected log output:
```
INFO:hf_sync:============================================================
INFO:hf_sync:Starting HuggingFace LiteRT Model Sync
INFO:hf_sync:============================================================
INFO:hf_sync:Starting fetch of LiteRT models from HuggingFace...
INFO:hf_sync:Fetched 763 LiteRT models from HuggingFace
INFO:hf_sync:Sync completed - Created: 150, Updated: 5, Skipped: 2
INFO:hf_sync:============================================================
INFO:hf_sync:HuggingFace LiteRT Model Sync Completed Successfully
INFO:hf_sync:Results: {'created': 150, 'updated': 5, 'skipped': 2}
INFO:hf_sync:============================================================
```

### Method 3: Database Queries

**Check total synced models:**
```sql
SELECT COUNT(*) as total_synced_models 
FROM ml_models 
WHERE hf_model_id IS NOT NULL;

-- Expected: Should match the "created" count from last sync
```

**View recent synced models:**
```sql
SELECT 
    id,
    name, 
    hf_model_id,
    category,
    task,
    created_at
FROM ml_models 
WHERE hf_model_id IS NOT NULL 
ORDER BY created_at DESC 
LIMIT 10;
```

**Check system user:**
```sql
SELECT id, username, email, is_developer 
FROM users 
WHERE username = 'hf_sync_system';
```

**Find models by task:**
```sql
SELECT 
    name, 
    hf_model_id, 
    task,
    tags
FROM ml_models 
WHERE hf_model_id IS NOT NULL 
AND task = 'image-classification'
LIMIT 20;
```

**Find models by category:**
```sql
SELECT 
    name,
    category,
    license_type,
    created_at
FROM ml_models 
WHERE hf_model_id IS NOT NULL 
AND category = 'utility'
ORDER BY created_at DESC
LIMIT 10;
```

---

## Testing Specific Scenarios

### Scenario 1: First-Time Sync

**Steps:**
1. Ensure database is clean: `DELETE FROM ml_models WHERE hf_model_id IS NOT NULL;`
2. Trigger manual sync
3. Check response: should show `created: ~150-200`, `updated: 0`, `skipped: 0-5`

**Verification:**
```sql
SELECT COUNT(*) FROM ml_models WHERE hf_model_id IS NOT NULL;
-- Should be ~150-200
```

### Scenario 2: Incremental Update (Re-run Same Sync)

**Steps:**
1. Trigger sync again immediately
2. Check response: should show `created: 0`, `updated: >0`, `skipped: ~same as before`

**Verification:**
```sql
SELECT COUNT(DISTINCT hf_model_id) FROM ml_models 
WHERE hf_model_id IS NOT NULL;
-- Should match total count (no duplicates)
```

### Scenario 3: User Can Create Version for Synced Model

**Steps:**
1. Pick a synced model ID from database
2. Call POST `/models/{model_id}/versions/{version_id}` with version data
3. Should succeed without errors

**Example:**
```bash
# Get a model
curl http://localhost:8000/models \
  -H "Authorization: Bearer TOKEN" | jq '.[] | select(.hf_model_id != null) | .id' | head -1

# Expected output: a UUID

# Create a version for it (substitute MODEL_ID)
curl -X POST http://localhost:8000/models/MODEL_ID/versions/VERSION_ID \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "version_string": "1.0.0",
    "changelog": "Initial version",
    "pipeline_spec": {
      "input_nodes": ["input"],
      "output_nodes": ["output"]
    },
    "assets": []
  }'
```

### Scenario 4: Browsing Synced Models via API

**Get all synced models:**
```bash
curl http://localhost:8000/models \
  -H "Authorization: Bearer TOKEN"
```

**Filter to just HF models:**
```bash
curl http://localhost:8000/models \
  -H "Authorization: Bearer TOKEN" | jq '.[] | select(.hf_model_id != null)'
```

**Get detail for one model:**
```bash
# First get a model ID
MODEL_ID=$(curl http://localhost:8000/models \
  -H "Authorization: Bearer TOKEN" | \
  jq -r '.[] | select(.hf_model_id != null) | .id' | head -1)

# Get details
curl http://localhost:8000/models/$MODEL_ID \
  -H "Authorization: Bearer TOKEN"
```

---

## Expected Data Structure

### Synced Model Example

Database entry:
```sql
SELECT * FROM ml_models 
WHERE hf_model_id = 'google/mobilenet_v1' 
LIMIT 1;
```

Output:
```
id                   | a1b2c3d4-e5f6-4789-0123-456789abcdef
name                 | mobilenet_v1
slug                 | google-mobilenet_v1
description          | MobileNet v1 model from HuggingFace
category             | utility
hf_model_id          | google/mobilenet_v1
license_type         | apache-2.0
origin_repo_url      | https://huggingface.co/google/mobilenet_v1
author_id            | hf_sync_system_id (uuid)
tags                 | ["vision", "image-classification"]
task                 | image-classification
is_verified_official | false
total_download_count | 0
rating_weighted_avg  | 0.0
total_ratings        | 0
created_at           | 2024-02-17 10:15:00
```

### API Response Example

GET `/models/a1b2c3d4-e5f6-4789-0123-456789abcdef`

```json
{
  "name": "mobilenet_v1",
  "slug": "google-mobilenet_v1",
  "description": "MobileNet v1 model from HuggingFace",
  "category": "utility",
  "id": "a1b2c3d4-e5f6-4789-0123-456789abcdef",
  "author_id": "hf_sync_system_id",
  "tags": ["vision", "image-classification"],
  "task": "image-classification",
  "license_type": "apache-2.0",
  "total_download_count": 0,
  "rating_weighted_avg": 0.0,
  "total_ratings": 0,
  "created_at": "2024-02-17T10:15:00"
}
```

---

## Performance Testing

### Test Sync Performance

```bash
# Time the sync
$start = Get-Date
# (trigger sync endpoint)
$end = Get-Date
"Sync took: $($end - $start)"

# Expected: 30-60 seconds for first sync, <10 seconds for incremental
```

### Test Database Performance

```sql
-- Check if indexes exist
SELECT * FROM information_schema.indexes 
WHERE table_name = 'ml_models';

-- Query performance
EXPLAIN ANALYZE
SELECT COUNT(*) FROM ml_models WHERE hf_model_id IS NOT NULL;

-- Should use index efficiently
```

---

## Debugging Tips

### Enable Verbose Logging

In `hf_sync.py`, change:
```python
logging.basicConfig(level=logging.DEBUG)  # Was INFO
```

This will show more detailed logs including each model being processed.

### Test HF API Directly

```python
from huggingface_hub import HfApi

api = HfApi()
models = list(api.list_models(filter="LiteRT", limit=5))

for m in models:
    print(f"{m.id}: {m.pipeline_tag}")
```

### Check Scheduler Status

Add this temporary endpoint to test:
```python
@app.get("/admin/scheduler")
def scheduler_status():
    return {
        "running": scheduler.running,
        "jobs": [(job.id, str(job.next_run_time)) for job in scheduler.get_jobs()]
    }
```

Then visit: `http://localhost:8000/admin/scheduler`

---

## Cleanup

### Delete All Synced Models (Dangerous!)

```sql
DELETE FROM ml_models WHERE hf_model_id IS NOT NULL;
DELETE FROM users WHERE username = 'hf_sync_system';
```

### Delete Synced Models by Task

```sql
DELETE FROM ml_models 
WHERE hf_model_id IS NOT NULL 
AND task = 'image-classification';
```

### Verify No Orphaned Versions

```sql
SELECT v.* FROM model_versions v
LEFT JOIN ml_models m ON v.model_id = m.id
WHERE m.id IS NULL;

-- Should return 0 rows (no orphaned versions)
```

---

## Common Testing Issues

### Issue: "Sync fails with HF API error"
- Check internet connection
- Verify HF API is accessible: `ping api-inference.huggingface.co`
- Check rate limits - HF might be rate limiting you

### Issue: "Database errors during sync"
- Ensure database is running
- Check PostgreSQL connection string in `.env`
- Verify `ml_models` table exists

### Issue: "Models not visible in browse page"
- Check that models were actually created in DB
- Verify API endpoint is returning models
- Check web app is making correct API call

### Issue: "Can't create version for synced model"
- Make sure model ID is correct (use UUID from DB)
- Make sure version ID is a unique UUID
- Make sure required fields are provided

---

## Success Criteria

✅ All these should pass:

1. **Sync Triggers Without Error**
   - Manual sync endpoint returns status "success"

2. **Models Exist in Database**
   - Query returns ~150+ models with hf_model_id not null

3. **Models Visible in API**
   - GET /models returns models with filled hf_model_id

4. **Models Visible in Web UI**
   - Browse page shows many new models

5. **Can Create Version**
   - POST /models/{id}/versions succeeds for synced model

6. **System User Exists**
   - Query shows "hf_sync_system" user in database

7. **Scheduler Running**
   - Logs show "scheduler started" on app startup

---

Need more help? Check the main guide: **HF_SYNC_GUIDE.md**
