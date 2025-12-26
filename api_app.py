"""FastAPI entrypoint for uvicorn.

Run: `uvicorn api_app:app --reload`
Supports both `/` and `/api` paths for local parity with Vercel.
"""

from fastapi import FastAPI

from child_story_maker.backend.app import app as core_app

app = FastAPI()
app.mount("/api", core_app)
app.mount("/", core_app)
