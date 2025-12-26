# Deploy to Vercel + Supabase (step-by-step)

This project deploys as:
- **Frontend:** static site from `web/` on Vercel
- **API:** Python serverless function on Vercel (`/api/*`)
- **Database:** Supabase Postgres (Auth + children + stories)
- **Media:** Supabase Storage (images/audio)

## 0) Prerequisites

- A GitHub repo containing this project.
- A Supabase account.
- A Vercel account.

## 1) Supabase setup

1. Create a new Supabase project.
2. Go to **SQL Editor** → run `supabase/schema.sql`.
3. Go to **Authentication** → enable **Email** provider (default).
4. Go to **Storage** → create a bucket named `story-media`.
   - Set the bucket to **Public** (so the web UI can display image URLs).
5. Go to **Project Settings → API** and copy:
   - Project URL
   - `anon` public key
   - `service_role` secret key (**keep this private; backend only**)

## 2) Frontend config

Open `web/config.js` and set:
- `supabaseUrl` = your Supabase Project URL
- `supabaseAnonKey` = your Supabase anon key

`apiBase` auto-uses:
- `""` on localhost
- `"/api"` on Vercel

## 3) Vercel deploy

1. Push your code to GitHub (do not commit `.env` or any secrets).
2. In Vercel: **New Project** → import your GitHub repo.
3. In Vercel: **Project Settings → Environment Variables**, add:
   - `OPENAI_API_KEY` = your OpenAI key
   - `SUPABASE_URL` = your Supabase Project URL
   - `SUPABASE_ANON_KEY` = your Supabase anon key
   - `SUPABASE_SERVICE_ROLE_KEY` = your Supabase service role key
   - `SUPABASE_STORAGE_BUCKET` = `story-media`
   - `USE_LOCAL_DB` = `0`
   - `DISABLE_LOCAL_MEDIA` = `1`
4. Deploy.

When it’s live:
- Website: `https://<your-project>.vercel.app`
- API: `https://<your-project>.vercel.app/api/health`

## 4) Local run (optional)

1. Install deps:
   - `pip install -r requirements.txt`
2. Create `.env` (local) and set:
   - `OPENAI_API_KEY=...`
3. Run:
   - `uvicorn api_app:app --reload`
4. Open:
   - `http://127.0.0.1:8000`

## Notes

- **Do not commit secrets** (OpenAI key, Supabase service role key). Rotate any leaked keys.
- On serverless, image generation is done **per section** via:
  - `POST /api/story/{story_id}/sections/{section_id}/image`
  to avoid long-running single requests.
