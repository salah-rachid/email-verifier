-- Supabase PostgreSQL schema for EmailVerifier

create extension if not exists pgcrypto;

create table if not exists users (
    id uuid primary key default gen_random_uuid(),
    email text not null unique,
    password_hash text not null,
    api_key text not null unique default encode(gen_random_bytes(24), 'hex'),
    credits integer not null default 100,
    created_at timestamptz not null default now(),
    constraint ck_users_credits_non_negative check (credits >= 0)
);

create table if not exists jobs (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users (id) on delete cascade,
    filename text not null,
    total_emails integer not null default 0,
    processed integer not null default 0,
    valid_count integer not null default 0,
    risky_count integer not null default 0,
    invalid_count integer not null default 0,
    status text not null default 'queued',
    r2_file_key text,
    created_at timestamptz not null default now(),
    finished_at timestamptz,
    constraint ck_jobs_total_emails_non_negative check (total_emails >= 0),
    constraint ck_jobs_processed_non_negative check (processed >= 0),
    constraint ck_jobs_valid_count_non_negative check (valid_count >= 0),
    constraint ck_jobs_risky_count_non_negative check (risky_count >= 0),
    constraint ck_jobs_invalid_count_non_negative check (invalid_count >= 0),
    constraint ck_jobs_status_allowed check (status in ('queued', 'running', 'done', 'cancelled')),
    constraint ck_jobs_processed_lte_total check (processed <= total_emails),
    constraint ck_jobs_counts_lte_processed check (valid_count + risky_count + invalid_count <= processed)
);

create index if not exists idx_jobs_user_id on jobs (user_id);
create index if not exists idx_jobs_status on jobs (status);

create table if not exists email_cache (
    email text primary key,
    status text not null,
    reason text not null,
    checked_at timestamptz not null default now(),
    expires_at timestamptz generated always as (checked_at + interval '30 days') stored,
    constraint ck_email_cache_status_allowed check (status in ('valid', 'risky', 'invalid'))
);

create index if not exists idx_email_cache_expires_at on email_cache (expires_at);

create table if not exists probe_servers (
    id uuid primary key default gen_random_uuid(),
    ip_address inet not null unique,
    probes_today integer not null default 0,
    is_active boolean not null default true,
    last_banned_at timestamptz,
    daily_limit integer not null default 200,
    constraint ck_probe_servers_probes_today_non_negative check (probes_today >= 0),
    constraint ck_probe_servers_daily_limit_positive check (daily_limit > 0)
);
