# Child Story Maker

Create personalized, illustrated children’s stories with a static web UI and a FastAPI backend.

Key features:
- Parent login + multiple child profiles (name, age, interests)
- Story generation with kid-safe prompts
- Story library (open, delete, download PDF/ZIP)
- Share links (public read-only)
- Safety & reading report
- Learning pack (summary, questions, vocabulary)
- Read-aloud narration (OpenAI TTS)

## Project Layout

```
.
├─ api/                         # Vercel serverless entrypoint
├─ api_app.py                   # FastAPI entrypoint for local uvicorn
├─ child_story_maker/
│  ├─ backend/                  # FastAPI backend code
│  ├─ common/                   # Shared models + helpers
├─ supabase/                    # SQL schema for Supabase
├─ web/                         # Static web UI (HTML/CSS/JS)
├─ media/                       # Generated images/audio (runtime)
```

## Setup

1) Create a virtualenv and install deps:
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

2) Create `.env` in the repo root:
```ini
OPENAI_API_KEY=your_key_here
USE_LOCAL_DB=1
```

Optional config:
```ini
STORY_MODEL=gpt-4o-mini
LEARNING_MODEL=gpt-4o-mini
IMAGE_MODEL=dall-e-2
IMAGE_FALLBACK_MODELS=dall-e-2
IMAGE_SIZE=512x512
IMAGE_QUALITY=low
TTS_MODEL=gpt-4o-mini-tts
STORY_API_BASE_URL=http://127.0.0.1:8000
```

## Run (Local)

1) Start the API:
```bash
uvicorn api_app:app --reload
```
Docs: `http://127.0.0.1:8000/docs`

2) Open the web app:
`http://127.0.0.1:8000`

## Docker

Build:
```bash
docker build -t child-story-maker .
```

Run:
```bash
docker run --rm -p 8000:8000 -e OPENAI_API_KEY=your_key child-story-maker
```

## Cloud Deploy (Vercel + Supabase)

This setup deploys the web UI + API on Vercel and uses Supabase for auth, storage,
and story persistence.

1) Create a Supabase project.
2) In Supabase SQL editor, run `supabase/schema.sql`.
3) Create a Storage bucket named `story-media` and set it to public.
4) Enable Email auth in Supabase.
5) Set `web/config.js` with your Supabase URL + anon key.
6) Add Vercel env vars:
   - `OPENAI_API_KEY`
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `SUPABASE_STORAGE_BUCKET=story-media`
   - `USE_LOCAL_DB=0`
   - `DISABLE_LOCAL_MEDIA=1`

After deploy, the web app calls `/api/*` on Vercel and stores data in Supabase.
