# Quick Start Guide - HuggingFace LiteRT Auto-Sync

## 5-Minute Setup

### 1. Install Dependencies
```bash
cd model-service/backend
pip install -r requirements.txt
```

### 2. Restart API Server
```bash
# If using FastAPI CLI
fastapi dev api.py

# Or using Uvicorn
python -m uvicorn api:app --reload
```

### 3. Look for This Log Message
```
INFO:root:Background scheduler started - HF LiteRT sync scheduled for 02:00 UTC daily
```

**Done!** The system is now active and will sync models daily at 2 AM UTC.

---

## Test It Now (Optional)

### Get an Auth Token
First, log in and get a valid JWT token from your auth system.

### Trigger Manual Sync
```bash
curl -X POST http://localhost:8000/sync/huggingface/litert \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json"
```

### Expected Response
```json
{
  "status": "success",
  "created": 150,
  "updated": 0,
  "skipped": 2,
  "message": "Successfully synced LiteRT models. Created: 150, Updated: 0, Skipped: 2"
}
```

### Check Models in Browser
Visit: `http://localhost:5173/browse`

You should now see ~150 new LiteRT models from HuggingFace!

---

## What Happened?

🔧 **3 Files Created:**
1. `hf_sync.py` - The sync engine
2. `requirements.txt` - Dependencies
3. `HF_SYNC_GUIDE.md` - Full documentation
4. `SYNC_IMPLEMENTATION_NOTES.md` - Architecture details

✏️ **1 File Modified:**
1. `api.py` - Added scheduler and sync endpoint

📊 **Result:**
- ~763 public LiteRT models from HF are now automatically available
- New models appear daily (2 AM UTC)
- Users can create versions without manual upload
- Manual trigger available via API endpoint

---

## Key Features

✅ **Automatic** - Runs daily at 2 AM UTC  
✅ **Incremental** - Only creates new models, updates metadata  
✅ **Resilient** - Skips errors, continues processing  
✅ **Triggerable** - Manual sync via API endpoint  
✅ **Logged** - Complete audit trail  
✅ **Smart** - No versions created (users do this manually)  

---

## Common Tasks

### Change Sync Time
Edit `api.py`, find `CronTrigger(hour=2, minute=0)`, change the hour.

### Check Sync Count
```sql
SELECT COUNT(*) FROM ml_models WHERE hf_model_id IS NOT NULL;
```

### View Recent Syncs
```sql
SELECT name, hf_model_id, created_at FROM ml_models 
WHERE hf_model_id IS NOT NULL 
ORDER BY created_at DESC LIMIT 20;
```

### View Logs
Check application console output for `hf_sync` prefix.

---

## Troubleshooting

**Models not appearing?**
- Check logs for errors
- Verify database connection
- Trigger manual sync to test

**Scheduler not running?**
- Verify APScheduler installed: `pip list | grep APScheduler`
- Check for startup errors in logs

**API errors?**
- Ensure you have valid JWT token
- Check internet connection to HuggingFace

---

## Documentation Files

📖 **Read for more info:**
- `HF_SYNC_GUIDE.md` - Complete reference guide
- `SYNC_IMPLEMENTATION_NOTES.md` - Architecture & impact
- `HF_SYNC_TEST_EXAMPLES.md` - Examples & queries

---

**That's it!** Your Pocket AI now auto-syncs LiteRT models from HuggingFace.
