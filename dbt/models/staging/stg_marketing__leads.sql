{{ config(materialized='view') }}

{#
    Staging model — one per source table, 1:1 with c360.bronze_dev.marketing_leads.
    Scope: rename + cast + light cleanup only. No joins, no dedup, no filters,
    no business logic. Downstream models reference this model, never bronze directly.
    Raw columns are all STRING (bronze keeps data exactly as received).
    HubSpot-style raw names (firstname, createdate, lifecyclestage) renamed to
    snake_case conventions used across the project.
    Validated against data 2026-11-18: lead_id unique, email and createdate
    always present, createdate/lastmodifieddate are ISO 'Z' strings that cast
    to timestamp, lifecyclestage in {lead, customer, marketingqualifiedlead,
    opportunity, subscriber}, lead_source title-cased, _rescued_data empty.
#}

with source as (

    select * from {{ source('bronze', 'marketing_leads') }}

),

staged as (

    select

        -- Keys & identity
        nullif(trim(lead_id), '')                       as lead_id,          -- grain of this table
        nullif(trim(firstname), '')                     as first_name,       -- raw: 'firstname'
        nullif(trim(lastname), '')                      as last_name,       -- raw: 'lastname'
        nullif(lower(trim(email)), '')                  as email,            -- lowercased: identity-resolution candidate
        nullif(trim(phone), '')                        as phone,

        -- Company & funnel
        nullif(trim(company), '')                       as company,
        nullif(trim(lifecyclestage), '')               as lifecycle_stage,  -- raw: 'lifecyclestage', lowercase values
        nullif(trim(lead_source), '')                   as lead_source,      -- title-cased values kept as-is

        -- Timestamps (ISO 'Z' strings in raw)
        try_cast(createdate as timestamp)               as created_at,       -- raw: 'createdate'
        try_cast(lastmodifieddate as timestamp)         as last_modified_at, -- raw: 'lastmodifieddate'

        -- Loader metadata passthrough (audit / row-level lineage)
        _batch_data,
        _source_file,
        _loaded_at
        -- _rescued_data intentionally dropped (empty as of 2026-11-18). If Auto
        -- Loader ever rescues a column, re-add it here so schema drift is visible.

    from source

)

select * from staged
