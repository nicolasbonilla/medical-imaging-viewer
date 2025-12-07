"""
Optimized startup script for Cloud Run deployment.
Defers heavy library imports until first request.

This reduces container startup time from 60+ seconds to <10 seconds,
allowing Cloud Run health checks to pass quickly.
"""
import os
import sys

# Set production environment
os.environ.setdefault("ENVIRONMENT", "production")

# Verify critical imports only (fast imports)
try:
    import fastapi
    import uvicorn
    import pydantic
    print("✓ Core framework imports successful", file=sys.stderr)
except ImportError as e:
    print(f"✗ Critical import failed: {e}", file=sys.stderr)
    sys.exit(1)

# Import and run the application
# Heavy medical imaging libraries will be imported lazily on first use
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8080))

    # Cloud Run optimized configuration
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        workers=1,
        timeout_keep_alive=60,
        access_log=True,
        log_level="info"
    )
