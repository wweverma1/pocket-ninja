import os
import sys

try:
    from app import app
    from app.utils.worker import product_sync_worker
    print("App imported successfully")
except Exception as e:
    print(f"Failed to import app: {e}")
    sys.exit(1)

if __name__ == "__main__":
    print("Starting Pocket Ninja Background Worker...")
    
    try:
        product_sync_worker(app)
    except KeyboardInterrupt:
        print("Worker stopped manually.")
    except Exception as e:
        print(f"Worker crashed with error: {e}")
        sys.exit(1)