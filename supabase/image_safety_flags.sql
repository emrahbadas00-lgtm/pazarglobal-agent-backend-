-- Vision safety flag log table (no auto-ban)
-- Stores unsafe/illegal image attempts for admin review

-- ensure uuid generation is available (Supabase prefers gen_random_uuid)
create extension if not exists "pgcrypto";

create table if not exists public.image_safety_flags (
    id uuid primary key default gen_random_uuid(),
    user_id uuid null references auth.users (id) on delete set null,
    image_url text null,
    flag_type text not null check (flag_type in (
        'none','weapon','drugs','violence','abuse','terrorism','stolen','document','sexual','hate','unknown'
    )),
    confidence text not null check (confidence in ('high','medium','low')),
    message text not null,
    status text not null default 'pending' check (status in ('pending','confirmed','dismissed','banned')),
    created_at timestamptz not null default now(),
    reviewed_at timestamptz null,
    reviewer text null,
    notes text null
);

-- indexes for fast triage
create index if not exists idx_image_safety_flags_user_id on public.image_safety_flags(user_id);
create index if not exists idx_image_safety_flags_status on public.image_safety_flags(status);
create index if not exists idx_image_safety_flags_created_at on public.image_safety_flags(created_at desc);
create index if not exists idx_image_safety_flags_flag_status on public.image_safety_flags(flag_type, status);
