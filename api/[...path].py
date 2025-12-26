from fastapi import FastAPI

from child_story_maker.backend.app import app as core_app

app = FastAPI()
app.mount("/api", core_app)
