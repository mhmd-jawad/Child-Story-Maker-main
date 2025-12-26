# Deploy to Vercel + Supabase

This project deploys as:
- Frontend: static site from `web/` on Vercel
- API: Python serverless function on Vercel (`/api/*`)
- Database: Supabase Postgres (auth, children, stories)
- Media: Supabase Storage (images/audio)

## 1) Supabase setup

1. Create a Supabase project.
2. SQL Editor: run `supabase/schema.sql`.
3. Authentication: enable Email provider.
4. Storage: create bucket `story-media` and set it to public.
5. Project Settings → API:
   - Project URL
   - `anon` public key
   - `service_role` secret key (backend only)

## 2) Frontend config

Open `web/config.js` and set:
- `supabaseUrl` = your Supabase Project URL
- `supabaseAnonKey` = your Supabase anon key

`apiBase` auto-uses:
- `""` on localhost
- `"/api"` on Vercel

## 3) Vercel deploy

1. Push the repo to GitHub (do not commit `.env` or secrets).
2. Vercel: New Project → import the repo.
3. Vercel → Project Settings → Environment Variables:
   - `OPENAI_API_KEY`
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `SUPABASE_STORAGE_BUCKET=story-media`
   - `USE_LOCAL_DB=0`
   - `DISABLE_LOCAL_MEDIA=1`
4. Deploy.

When live:
- Web: `https://<your-project>.vercel.app`
- API: `https://<your-project>.vercel.app/api/health`

## 4) Local run (optional)

1. Install deps:
   - `pip install -r requirements.txt`
2. Create `.env` and set:
   - `OPENAI_API_KEY=...`
3. Run:
   - `uvicorn api_app:app --reload`
4. Open:
   - `http://127.0.0.1:8000`

## Notes

- Do not commit secrets (OpenAI or Supabase service role key).
- Image generation is done per section via:
  `POST /api/story/{story_id}/sections/{section_id}/image`
  to avoid long-running requests in serverless.
