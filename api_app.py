"""FastAPI entrypoint for uvicorn.

Run: `uvicorn api_app:app --reload`
"""

from child_story_maker.backend.app import app

