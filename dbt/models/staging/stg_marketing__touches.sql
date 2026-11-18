{{ config(materialized='view') }}

{#
    Staging model — one per source table, 1:1 with c360.bronze_dev.marketing_touches.
    Scope: rename + cast + light cleanup only. No joins, no dedup, no filters,
    no business logic. Downstream models reference this model, never bronze directly.
    Raw columns are all STRING (bronze keeps data exactly as received).
    Validated against data 2026-11-18: touch_id unique, lead_id always present,
    touch_ts is an ISO 'Z' string that casts to timestamp, touch_type in
    {email_open, webinar, demo_request, email_click, form_fill},
    _rescued_data empty.
#}

with source as (

    select * from {{ source('bronze', 'marketing_touches') }}

),

staged as (

    select

        -- Keys
        nullif(trim(touch_id), '')                       as touch_id,         -- grain of this table
        nullif(trim(lead_id), '')                       as lead_id,          -- FK → stg_marketing__leads

        -- Touch facts
        nullif(trim(touch_type), '')                    as touch_type,       -- lowercase values kept as-is
        nullif(trim(campaign), '')                      as campaign,
        try_cast(touch_ts as timestamp)                 as touched_at,       -- raw: 'touch_ts', ISO 'Z' string

        -- Loader metadata passthrough (audit / row-level lineage)
        _batch_data,
        _source_file,
        _loaded_at
        -- _rescued_data intentionally dropped (empty as of 2026-11-18). If Auto
        -- Loader ever rescues a column, re-add it here so schema drift is visible.

    from source

)

select * from staged
