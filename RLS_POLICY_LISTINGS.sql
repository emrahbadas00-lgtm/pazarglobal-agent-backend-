-- RLS policy for listings: only owner can select/update/delete
-- Enable RLS
alter table public.listings enable row level security;

-- Optional: drop existing overly-permissive policies first (manual step)
-- drop policy if exists "select_listings_owner" on public.listings;
-- drop policy if exists "update_listings_owner" on public.listings;
-- drop policy if exists "delete_listings_owner" on public.listings;

-- Select
create policy if not exists "select_listings_owner" on public.listings
for select
using (auth.uid() = user_id);

-- Update
create policy if not exists "update_listings_owner" on public.listings
for update
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

-- Delete
create policy if not exists "delete_listings_owner" on public.listings
for delete
using (auth.uid() = user_id);
