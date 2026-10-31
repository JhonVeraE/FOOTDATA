-- FOOTDATA · Base de datos (Supabase / Postgres)
-- Ejecutar una vez en: Supabase → SQL Editor → New query → pegar todo → Run.
-- Es idempotente: se puede volver a ejecutar sin perder datos.

-- ───────────────────────── Administradores iniciales ─────────────────────────
-- Correos que reciben el rol de administrador al registrarse (o ya registrados).
create table if not exists public.admin_emails (
  email text primary key check (email = lower(email))
);
alter table public.admin_emails enable row level security;
insert into public.admin_emails(email) values ('jaestelag@gmail.com'), ('veraejhonantony@gmail.com') on conflict do nothing;

-- ───────────────────────────────── Perfiles ──────────────────────────────────
create table if not exists public.profiles (
  id              uuid primary key references auth.users(id) on delete cascade,
  email           text not null,
  display_name    text check (char_length(display_name) <= 60),
  role            text not null default 'user'  check (role in ('user','admin')),
  plan            text not null default 'free'  check (plan in ('free','premium')),
  plan_expires_at timestamptz,
  favorite_teams  text[] not null default '{}' check (cardinality(favorite_teams) <= 30),
  created_at      timestamptz not null default now(),
  last_seen_at    timestamptz
);
alter table public.profiles enable row level security;

create or replace function public.is_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select exists(select 1 from public.profiles where id = auth.uid() and role = 'admin');
$$;

-- Crea el perfil al registrarse; asigna admin si el correo está en admin_emails.
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles(id, email, display_name, role)
  values (new.id, lower(new.email),
          nullif(left(coalesce(new.raw_user_meta_data->>'display_name', new.raw_user_meta_data->>'full_name', ''), 60), ''),
          case when exists(select 1 from public.admin_emails a where a.email = lower(new.email)) then 'admin' else 'user' end)
  on conflict (id) do nothing;
  return new;
end $$;
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

-- Perfiles de usuarios que ya existieran antes de este script.
insert into public.profiles(id, email, role)
select u.id, lower(u.email),
       case when exists(select 1 from public.admin_emails a where a.email = lower(u.email)) then 'admin' else 'user' end
from auth.users u on conflict (id) do nothing;
update public.profiles p set role = 'admin'
where p.email in (select email from public.admin_emails) and p.role <> 'admin';

-- Cada usuario ve y edita solo su perfil; el admin ve todos.
drop policy if exists profiles_select on public.profiles;
create policy profiles_select on public.profiles for select to authenticated
  using (id = auth.uid() or public.is_admin());
drop policy if exists profiles_update_own on public.profiles;
create policy profiles_update_own on public.profiles for update to authenticated
  using (id = auth.uid()) with check (id = auth.uid());
-- Rol y plan NO se pueden cambiar desde el navegador: solo nombre, favoritos y última visita.
revoke update on public.profiles from authenticated, anon;
grant select on public.profiles to authenticated;
grant update (display_name, favorite_teams, last_seen_at) on public.profiles to authenticated;

-- ─────────────────────────── Fijas guardadas por usuario ─────────────────────
create table if not exists public.saved_picks (
  user_id     uuid not null references auth.users(id) on delete cascade default auth.uid(),
  fixture_id  text not null check (char_length(fixture_id) <= 40),
  pick_id     text not null check (char_length(pick_id) <= 120),
  label       text not null check (char_length(label) <= 200),
  match_label text check (char_length(match_label) <= 200),
  kickoff_utc timestamptz,
  created_at  timestamptz not null default now(),
  primary key (user_id, fixture_id, pick_id)
);
alter table public.saved_picks enable row level security;
drop policy if exists saved_picks_own on public.saved_picks;
create policy saved_picks_own on public.saved_picks for all to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());
grant select, insert, delete on public.saved_picks to authenticated;

-- ───────────────────────────────── Avisos ────────────────────────────────────
-- Mensaje que el administrador publica arriba de la web.
create table if not exists public.announcements (
  id         bigint generated always as identity primary key,
  body       text not null check (char_length(body) between 1 and 280),
  link_url   text check (link_url is null or link_url ~ '^https://'),
  active     boolean not null default true,
  created_at timestamptz not null default now(),
  created_by uuid references auth.users(id) default auth.uid()
);
alter table public.announcements enable row level security;
drop policy if exists announcements_read on public.announcements;
create policy announcements_read on public.announcements for select to anon, authenticated
  using (active or public.is_admin());
drop policy if exists announcements_admin on public.announcements;
create policy announcements_admin on public.announcements for all to authenticated
  using (public.is_admin()) with check (public.is_admin());
grant select on public.announcements to anon, authenticated;
grant insert, update, delete on public.announcements to authenticated;

-- ──────────────────────────── Funciones del panel admin ──────────────────────
create or replace function public.admin_set_user(target uuid, new_role text, new_plan text, new_expires timestamptz default null)
returns void language plpgsql security definer set search_path = public as $$
begin
  if not public.is_admin() then raise exception 'Solo administradores'; end if;
  if new_role not in ('user','admin') or new_plan not in ('free','premium') then raise exception 'Valor no válido'; end if;
  if target = auth.uid() and new_role <> 'admin' then raise exception 'No puedes quitarte el rol de administrador'; end if;
  update public.profiles set role = new_role, plan = new_plan,
         plan_expires_at = case when new_plan = 'premium' then new_expires else null end
  where id = target;
end $$;
revoke execute on function public.admin_set_user(uuid, text, text, timestamptz) from public, anon;
grant execute on function public.admin_set_user(uuid, text, text, timestamptz) to authenticated;

create or replace function public.admin_stats() returns json
language plpgsql stable security definer set search_path = public as $$
begin
  if not public.is_admin() then raise exception 'Solo administradores'; end if;
  return json_build_object(
    'users',        (select count(*) from public.profiles),
    'premium',      (select count(*) from public.profiles where plan = 'premium'),
    'admins',       (select count(*) from public.profiles where role = 'admin'),
    'new_7d',       (select count(*) from public.profiles where created_at > now() - interval '7 days'),
    'active_7d',    (select count(*) from public.profiles where last_seen_at > now() - interval '7 days'),
    'saved_picks',  (select count(*) from public.saved_picks));
end $$;
revoke execute on function public.admin_stats() from public, anon;
grant execute on function public.admin_stats() to authenticated;
