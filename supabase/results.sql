-- FOOTDATA · Resultados y estadísticas (solo administradores)
-- Ejecutar después de supabase/schema.sql. Idempotente.

create table if not exists public.match_results (
  match_id    text primary key,
  fixture_id  text,
  date        date not null,
  league      text not null,
  season      text,
  home        text not null,
  away        text not null,
  home_score  int,
  away_score  int,
  stats       jsonb not null default '{}'::jsonb,
  forecast    jsonb,
  source      text,
  source_url  text,
  updated_at  timestamptz not null default now()
);
create index if not exists match_results_date on public.match_results(date desc);
create index if not exists match_results_fixture on public.match_results(fixture_id);
create index if not exists match_results_teams on public.match_results(home, away);

create table if not exists public.pick_results (
  date         date not null,
  fixture_id   text not null,
  tier         text not null,
  selection_id text not null,
  match_label  text,
  market       text,
  label        text,
  probability  numeric,
  status       text not null check (status in ('won','lost','unverified','pending')),
  metric       text,
  actual_home  numeric,
  actual_away  numeric,
  reviewed_at  timestamptz,
  primary key (date, fixture_id, tier, selection_id)
);
create index if not exists pick_results_date on public.pick_results(date desc);

create table if not exists public.daily_reviews (
  date        date primary key,
  summary     jsonb not null default '{}'::jsonb,
  reviewed_at timestamptz,
  updated_at  timestamptz not null default now()
);

alter table public.match_results enable row level security;
alter table public.pick_results  enable row level security;
alter table public.daily_reviews enable row level security;

-- Solo administradores leen. Nadie escribe desde el navegador: el pipeline escribe con la clave secreta.
do $$ declare t text; begin
  foreach t in array array['match_results','pick_results','daily_reviews'] loop
    execute format('drop policy if exists %I on public.%I', t||'_admin_read', t);
    execute format('create policy %I on public.%I for select to authenticated using (public.is_admin())', t||'_admin_read', t);
    execute format('revoke all on public.%I from anon, authenticated', t);
    execute format('grant select on public.%I to authenticated', t);
  end loop;
end $$;

select 'Resultados listos' as estado;
