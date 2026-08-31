"""
Root-level WSGI shim so `gunicorn app:app` works when run from the repo
root - which is what Render's default Start Command does. The real app
lives in backend/app.py (it needs to run from inside backend/ so its own
`sys.path.insert` and relative imports like `from config import ...` and
`from routes.auth import ...` resolve correctly). This file loads that
module under a different internal name to avoid colliding with its own
filename, then re-exports its Flask `app` object.

If you're running locally, ignore this file - use `python backend/app.py`
or `cd backend && python app.py` as documented in the README.
"""

import importlib.util
import os

_backend_app_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend", "app.py")
_spec = importlib.util.spec_from_file_location("backend_app", _backend_app_path)
_backend_app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_backend_app)

app = _backend_app.app
