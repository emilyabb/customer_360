{{ config(materialized='view') }}

{#
    Staging model — one per source table, 1:1 with c360.bronze_dev.support_tickets.
    Scope: rename + cast + light cleanup only. No joins, no dedup, no filters,
    no business logic. Downstream models reference this model, never bronze directly.
    Raw columns are all STRING (bronze keeps data exactly as received).
    Validated against data 2026-11-18: ticket_id unique, requester_id always
    present, created_at always present, solved_at NULL on 15 unsolved tickets
    (expected — do not not_null-test it), timestamps are ISO 'Z' strings that
    cast cleanly, status in {solved, pending, open, new}, priority in
    {normal, high, low, urgent}, channel in {chat, email, phone, web},
    _rescued_data empty.
#}

with source as (

    select * from {{ source('bronze', 'support_tickets') }}

),

staged as (

    select

        -- Keys
        nullif(trim(ticket_id), '')                     as ticket_id,        -- grain of this table
        nullif(trim(requester_id), '')                  as requester_id,     -- FK → stg_support__requesters

        -- Ticket facts
        nullif(trim(subject), '')                        as subject,
        nullif(trim(priority), '')                      as priority,         -- lowercase values kept as-is
        nullif(trim(channel), '')                        as channel,          -- lowercase values kept as-is
        nullif(trim(status), '')                        as status,           -- lowercase values kept as-is

        -- Timestamps (ISO 'Z' strings in raw)
        try_cast(created_at as timestamp)              as created_at,
        try_cast(solved_at as timestamp)                as solved_at,        -- NULL on unsolved tickets

        -- Loader metadata passthrough (audit / row-level lineage)
        _batch_data,
        _source_file,
        _loaded_at
        -- _rescued_data intentionally dropped (empty as of 2026-11-18). If Auto
        -- Loader ever rescues a column, re-add it here so schema drift is visible.

    from source

)

select * from staged
