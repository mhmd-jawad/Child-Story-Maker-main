# Supabase setup

1) Create a new Supabase project.
2) Open the SQL editor and run `schema.sql`.
3) Enable Email auth in Authentication settings.
4) Create a Storage bucket (suggested name: `story-media`) and set it to public.
5) Copy the project URL and anon key into `web/config.js`.

If you previously created tables manually, re-running `schema.sql` will add missing columns
and update policies. If inserts fail with a not-null error on `user_id`, confirm the column
default is set to `auth.uid()`.
