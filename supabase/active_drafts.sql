-- Active drafts table for deterministic FSM
create table if not exists public.active_drafts (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.profiles(id) on delete cascade,
    state varchar(20) not null default 'DRAFT',
    listing_data jsonb not null default '{}',
    images text[] not null default '{}',
    vision_product jsonb not null default '{}',
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    unique(user_id)
);

create index if not exists idx_active_drafts_user_id on public.active_drafts(user_id);
