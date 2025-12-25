# Child Story Maker

Create illustrated children’s stories with a Streamlit UI and a FastAPI backend.

The backend uses OpenAI for:
- Story generation (text)
- Image generation (illustrations)
- Optional TTS (narration)

The project also includes an embeddings-based “child-story similarity” score against a TinyStories-style corpus. This score is a heuristic signal, not a safety guarantee.

## Project Layout

```
.
├─ app.py                      # Streamlit entrypoint
├─ api_app.py                  # FastAPI entrypoint (uvicorn)
├─ child_story_maker/          # Python package
│  ├─ backend/                 # FastAPI backend code
│  ├─ frontend/                # Streamlit UI + API client
│  ├─ common/                  # Shared models + helpers
│  └─ ml/                      # Embeddings + similarity
├─ data/                       # Datasets (CSV + raw text)
├─ artifacts/embeddings/       # Generated embedding artifacts (.npy/.json)
├─ scripts/                    # Utility scripts (fetch dataset, score story)
├─ assets/                     # Images for docs
└─ media/                      # Generated images/audio (runtime)
```

## Setup

1. Create a virtualenv and install deps:
   ```bash
   python -m venv venv
   venv\Scripts\activate   # Windows
   pip install -r requirements.txt
   ```

2. Create `.env` in the repo root:
   ```ini
   OPENAI_API_KEY=your_key_here
   ```

Optional config:
```ini
STORY_MODEL=gpt-4o-mini
IMAGE_MODEL=dall-e-2
IMAGE_FALLBACK_MODELS=gpt-image-1
IMAGE_SIZE=512x512
IMAGE_QUALITY=low
STORY_API_BASE_URL=http://127.0.0.1:8000
```

## Run

1. Start the API:
   ```bash
   uvicorn api_app:app --reload
   ```
   Docs: `http://127.0.0.1:8000/docs`

2. Open the web app:
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

## Parent Login + Child Profiles (Web UI)

The web UI supports a local parent account and multiple child profiles stored
in `data/app.db`. Child profiles include name, age, and interests. The story
builder uses the active child profile to:

- Use the child's name as the main character
- Include themes from the child's interests
- Set age-appropriate language complexity

## Embeddings Similarity (Optional)

This compares your generated story to a child-story corpus using sentence-transformer embeddings.

1. Install optional embedding deps (note: `sentence-transformers` pulls in `torch`):
   ```bash
   pip install -r requirements-embeddings.txt
   ```

2. Fetch the TinyStories validation split and convert to CSV:
   ```bash
   python scripts/fetch_tinystories.py
   ```

3. Build embeddings artifacts:
   ```bash
   python -m child_story_maker.ml.build_embeddings --data data/children_books.csv --out artifacts/embeddings --k 3
   ```
   This creates:
   - `artifacts/embeddings/children_books_embeddings.npy`
   - `artifacts/embeddings/children_books_avg_embedding.npy`
   - `artifacts/embeddings/children_books_index.json`

4. CLI scoring demo:
   ```bash
   python scripts/score_story.py --story-json path/to/story.json --k 3
   ```
