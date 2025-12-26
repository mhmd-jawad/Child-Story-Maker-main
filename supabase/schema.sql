create extension if not exists "pgcrypto";

create table if not exists public.children (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid(),
  name text not null,
  age int not null check (age between 2 and 12),
  interests text not null,
  created_at timestamptz not null default now()
);

-- If the table already existed, ensure required columns exist.
alter table public.children add column if not exists user_id uuid;
alter table public.children alter column user_id set default auth.uid();
alter table public.children add column if not exists parent_id uuid;
alter table public.children alter column parent_id set default auth.uid();
alter table public.children add column if not exists name text;
alter table public.children add column if not exists age int;
alter table public.children add column if not exists interests text;
alter table public.children add column if not exists created_at timestamptz;
alter table public.children alter column created_at set default now();

do $$
begin
  update public.children set user_id = coalesce(user_id, parent_id) where user_id is null;
  update public.children set parent_id = coalesce(parent_id, user_id) where parent_id is null;

  if not exists (select 1 from public.children where user_id is null) then
    alter table public.children alter column user_id set not null;
  end if;
  if not exists (select 1 from public.children where parent_id is null) then
    alter table public.children alter column parent_id set not null;
  end if;
exception when others then
  -- If there are existing rows with NULL ids, fix them manually then re-run.
end $$;

alter table public.children enable row level security;

drop policy if exists "Parents manage their children" on public.children;
create policy "Parents manage their children"
  on public.children
  for all
  using (auth.uid() = coalesce(parent_id, user_id))
  with check (auth.uid() = coalesce(parent_id, user_id));

create table if not exists public.stories (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid(),
  child_id uuid null references public.children(id) on delete set null,
  title text not null,
  prompt text not null,
  age_group text not null,
  language text not null,
  style text not null,
  model text null,
  input_tokens int null,
  output_tokens int null,
  total_tokens int null,
  created_at timestamptz not null default now()
);

alter table public.stories add column if not exists user_id uuid;
alter table public.stories alter column user_id set default auth.uid();
alter table public.stories add column if not exists parent_id uuid;
alter table public.stories alter column parent_id set default auth.uid();
alter table public.stories add column if not exists child_id uuid;
alter table public.stories add column if not exists title text;
alter table public.stories add column if not exists prompt text;
alter table public.stories add column if not exists age_group text;
alter table public.stories add column if not exists language text;
alter table public.stories add column if not exists style text;
alter table public.stories add column if not exists model text;
alter table public.stories add column if not exists input_tokens int;
alter table public.stories add column if not exists output_tokens int;
alter table public.stories add column if not exists total_tokens int;
alter table public.stories add column if not exists created_at timestamptz;
alter table public.stories alter column created_at set default now();

do $$
begin
  update public.stories set user_id = coalesce(user_id, parent_id) where user_id is null;
  update public.stories set parent_id = coalesce(parent_id, user_id) where parent_id is null;

  if not exists (select 1 from public.stories where user_id is null) then
    alter table public.stories alter column user_id set not null;
  end if;
  if not exists (select 1 from public.stories where parent_id is null) then
    alter table public.stories alter column parent_id set not null;
  end if;
exception when others then
end $$;

alter table public.stories enable row level security;

drop policy if exists "Parents manage their stories" on public.stories;
create policy "Parents manage their stories"
  on public.stories
  for all
  using (auth.uid() = coalesce(parent_id, user_id))
  with check (auth.uid() = coalesce(parent_id, user_id));

create table if not exists public.story_sections (
  story_id uuid not null references public.stories(id) on delete cascade,
  idx int not null check (idx >= 1),
  title text not null,
  text text not null,
  image_prompt text not null,
  image_url text null,
  audio_url text null,
  created_at timestamptz not null default now(),
  primary key (story_id, idx)
);

alter table public.story_sections add column if not exists story_id uuid;
alter table public.story_sections add column if not exists idx int;
alter table public.story_sections add column if not exists title text;
alter table public.story_sections add column if not exists text text;
alter table public.story_sections add column if not exists image_prompt text;
alter table public.story_sections add column if not exists image_url text;
alter table public.story_sections add column if not exists audio_url text;
alter table public.story_sections add column if not exists created_at timestamptz;
alter table public.story_sections alter column created_at set default now();

alter table public.story_sections enable row level security;

drop policy if exists "Parents manage their story sections" on public.story_sections;
create policy "Parents manage their story sections"
  on public.story_sections
  for all
  using (
    exists (
      select 1 from public.stories s
      where s.id = story_sections.story_id
        and coalesce(s.parent_id, s.user_id) = auth.uid()
    )
  )
  with check (
    exists (
      select 1 from public.stories s
      where s.id = story_sections.story_id
        and coalesce(s.parent_id, s.user_id) = auth.uid()
    )
  );

-- Public share links (token-based). Creation/deletion is owner-only.
create table if not exists public.story_shares (
  token uuid primary key default gen_random_uuid(),
  story_id uuid not null references public.stories(id) on delete cascade,
  user_id uuid not null default auth.uid(),
  created_at timestamptz not null default now(),
  expires_at timestamptz null
);

alter table public.story_shares add column if not exists story_id uuid;
alter table public.story_shares add column if not exists user_id uuid;
alter table public.story_shares alter column user_id set default auth.uid();
alter table public.story_shares add column if not exists parent_id uuid;
alter table public.story_shares alter column parent_id set default auth.uid();
alter table public.story_shares add column if not exists created_at timestamptz;
alter table public.story_shares alter column created_at set default now();
alter table public.story_shares add column if not exists expires_at timestamptz;

alter table public.story_shares enable row level security;
drop policy if exists "Owners manage story shares" on public.story_shares;
create policy "Owners manage story shares"
  on public.story_shares
  for all
  using (auth.uid() = coalesce(parent_id, user_id))
  with check (auth.uid() = coalesce(parent_id, user_id));

-- Learning pack (questions + vocabulary) per story
create table if not exists public.story_learning (
  story_id uuid primary key references public.stories(id) on delete cascade,
  user_id uuid not null default auth.uid(),
  created_at timestamptz not null default now(),
  summary text null,
  questions jsonb null,
  vocabulary jsonb null
);

alter table public.story_learning add column if not exists user_id uuid;
alter table public.story_learning alter column user_id set default auth.uid();
alter table public.story_learning add column if not exists parent_id uuid;
alter table public.story_learning alter column parent_id set default auth.uid();
alter table public.story_learning add column if not exists created_at timestamptz;
alter table public.story_learning alter column created_at set default now();
alter table public.story_learning add column if not exists summary text;
alter table public.story_learning add column if not exists questions jsonb;
alter table public.story_learning add column if not exists vocabulary jsonb;

alter table public.story_learning enable row level security;
drop policy if exists "Owners manage story learning" on public.story_learning;
create policy "Owners manage story learning"
  on public.story_learning
  for all
  using (auth.uid() = coalesce(parent_id, user_id))
  with check (auth.uid() = coalesce(parent_id, user_id));

-- Safety / evaluation report per story (JSON)
create table if not exists public.story_reports (
  story_id uuid primary key references public.stories(id) on delete cascade,
  user_id uuid not null default auth.uid(),
  created_at timestamptz not null default now(),
  report jsonb not null
);

alter table public.story_reports add column if not exists user_id uuid;
alter table public.story_reports alter column user_id set default auth.uid();
alter table public.story_reports add column if not exists parent_id uuid;
alter table public.story_reports alter column parent_id set default auth.uid();
alter table public.story_reports add column if not exists created_at timestamptz;
alter table public.story_reports alter column created_at set default now();
alter table public.story_reports add column if not exists report jsonb;

alter table public.story_reports enable row level security;
drop policy if exists "Owners manage story reports" on public.story_reports;
create policy "Owners manage story reports"
  on public.story_reports
  for all
  using (auth.uid() = coalesce(parent_id, user_id))
  with check (auth.uid() = coalesce(parent_id, user_id));
