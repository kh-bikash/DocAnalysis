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
    # Run uvicorn using the absolute module name "backend.app.main:app"
    # and specify app_dir as backend_dir so it watches for changes there
    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        app_dir=str(backend_dir)
    )
