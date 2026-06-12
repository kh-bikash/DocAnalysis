import os
import sys
from pathlib import Path
import uvicorn

# Get the folder containing run.py
backend_dir = Path(__file__).resolve().parent
parent_dir = backend_dir.parent

# Detect production environment: on Railway the Root Directory is set to 'backend/',
# so backend_dir IS the container root (/app) and parent_dir has no 'backend' subfolder.
# We need "from backend.app.xxx import" to work, so we add the parent to sys.path.
# But since parent_dir doesn't contain a 'backend' folder on Railway, we add backend_dir
# as 'backend' by creating a virtual package mapping.

# Always add parent_dir first (works locally where parent_dir contains backend/)
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

# Also ensure backend_dir itself is on path for any direct imports
if str(backend_dir) not in sys.path:
    sys.path.insert(1, str(backend_dir))

# Production fix: if there's no 'backend' package visible from parent_dir,
# create a symlink so that 'backend' resolves to the current directory.
backend_pkg = parent_dir / "backend"
if not backend_pkg.exists():
    try:
        # backend_dir IS the backend package - create symlink from parent/backend -> backend_dir
        os.symlink(str(backend_dir), str(backend_pkg), target_is_directory=True)
    except (OSError, NotImplementedError):
        # Fallback: insert backend_dir under the name 'backend' using sys.modules trick
        import types
        backend_module = types.ModuleType("backend")
        backend_module.__path__ = [str(backend_dir)]
        backend_module.__package__ = "backend"
        sys.modules["backend"] = backend_module


if __name__ == "__main__":
    # Read port from env (inserted by Railway/Render)
    port = int(os.environ.get("PORT", 8000))
    # Turn off reload in production
    is_prod = "RAILWAY_ENVIRONMENT" in os.environ or (
        "PORT" in os.environ and os.environ.get("PORT") != "8000"
    )
    reload_mode = not is_prod

    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=port,
        reload=reload_mode,
        app_dir=str(parent_dir)
    )
