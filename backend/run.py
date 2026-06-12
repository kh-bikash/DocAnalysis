import os
import sys
from pathlib import Path
import uvicorn

# Get the folder containing run.py (d:\Projects\DI\backend)
backend_dir = Path(__file__).resolve().parent
# Get the parent folder (d:\Projects\DI)
parent_dir = backend_dir.parent

# Add the parent folder to the Python path so "backend" is importable
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

# Add backend_dir to the Python path too, just in case
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

if __name__ == "__main__":
    # Read port from env (inserted by Railway/Render)
    port = int(os.environ.get("PORT", 8000))
    # Turn off reload in production to optimize performance
    is_prod = "RAILWAY_ENVIRONMENT" in os.environ or "PORT" in os.environ and os.environ.get("PORT") != "8000"
    reload_mode = not is_prod
    
    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=port,
        reload=reload_mode,
        app_dir=str(backend_dir)
    )
