-- Run once in Supabase > SQL Editor.
create table public.lots (
  id bigint generated always as identity primary key,
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  pid integer not null,            -- TCGplayer productId
  gid integer not null,            -- TCGplayer groupId (set)
  name text not null,
  qty numeric not null check (qty > 0),
  cost numeric not null check (cost >= 0),   -- per unit
  date date not null default current_date,
  created_at timestamptz not null default now()
);
create index lots_user_idx on public.lots(user_id);
alter table public.lots enable row level security;
create policy "own lots" on public.lots for all to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

-- Shared daily prices. Users can read; only the GitHub job (service key) can write.
create table public.prices (
  pid integer not null, date date not null, price numeric not null,
  primary key (pid, date)
);
alter table public.prices enable row level security;
create policy "read prices" on public.prices for select to authenticated using (true);

-- Correct qty / cost per unit for one SKU: replaces its lots with a single lot (earliest date kept). qty 0 removes it.
create or replace function public.edit_sku(p_pid int, p_qty numeric, p_cost numeric)
returns void language plpgsql security invoker as $$
declare d date; g int; n text;
begin
  select min(date) into d from public.lots where pid = p_pid;
  select gid, name into g, n from public.lots where pid = p_pid limit 1;
  delete from public.lots where pid = p_pid;
  if p_qty > 0 and d is not null then
    insert into public.lots(pid, gid, name, qty, cost, date) values (p_pid, g, n, p_qty, p_cost, d);
  end if;
end $$;
