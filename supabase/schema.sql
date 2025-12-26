create extension if not exists "pgcrypto";

create table if not exists public.children (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid not null default auth.uid(),
  name text not null,
  age int not null check (age between 2 and 12),
  interests text not null,
  created_at timestamptz not null default now()
);

alter table public.children enable row level security;

create policy "Parents manage their children"
  on public.children
  for all
  using (auth.uid() = parent_id)
  with check (auth.uid() = parent_id);
