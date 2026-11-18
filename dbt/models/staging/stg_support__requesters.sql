{{ config(materialized='view') }}

{#
    Staging model — one per source table, 1:1 with c360.bronze_dev.support_requesters.
    Scope: rename + cast + light cleanup only. No joins, no dedup, no filters,
    no business logic. Downstream models reference this model, never bronze directly.
    Raw columns are all STRING (bronze keeps data exactly as received).
    Validated against data 2026-11-18: requester_id unique, email and
    created_at always present, created_at is an ISO 'Z' string that casts to
    timestamp, _rescued_data empty.
#}

with source as (

    select * from {{ source('bronze', 'support_requesters') }}

),

staged as (

    select

        -- Keys & identity
        nullif(trim(requester_id), '')                   as requester_id,     -- grain of this table
        nullif(trim(name), '')                          as name,
        nullif(lower(trim(email)), '')                  as email,            -- lowercased: identity-resolution candidate
        nullif(trim(phone), '')                        as phone,
        nullif(trim(organization), '')                  as organization,

        -- Timestamps (ISO 'Z' strings in raw)
        try_cast(created_at as timestamp)              as created_at,

        -- Loader metadata passthrough (audit / row-level lineage)
        _batch_data,
        _source_file,
        _loaded_at
        -- _rescued_data intentionally dropped (empty as of 2026-11-18). If Auto
        -- Loader ever rescues a column, re-add it here so schema drift is visible.

    from source

)

select * from staged
