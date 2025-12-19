-- RLS policy for listings: Herkes aktif ilanları görebilir, sadece sahibi düzenleyebilir
-- Enable RLS
alter table public.listings enable row level security;

-- Eski kısıtlı policy'leri kaldır (önce çalıştır)
drop policy if exists "select_listings_owner" on public.listings;
drop policy if exists "update_listings_owner" on public.listings;
drop policy if exists "delete_listings_owner" on public.listings;
drop policy if exists "Anyone can view active listings" on public.listings;
drop policy if exists "Users can insert own listings" on public.listings;
drop policy if exists "Users can update own listings" on public.listings;
drop policy if exists "Users can delete own listings" on public.listings;

-- SELECT: Herkes aktif ilanları görebilir
create policy "public_can_view_active_listings" on public.listings
for select
using (status = 'active');

-- INSERT: Herkes ilan ekleyebilir (user_id otomatik atanır)
create policy "authenticated_can_insert_listings" on public.listings
for insert
with check (true);

-- UPDATE: Sadece kendi ilanını güncelleyebilir
create policy "owner_can_update_own_listings" on public.listings
for update
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

-- DELETE: Sadece kendi ilanını silebilir
create policy "owner_can_delete_own_listings" on public.listings
for delete
using (auth.uid() = user_id);
