{{ config(materialized='view') }}

{#
    Staging model — one per source table, 1:1 with c360.bronze_dev.crm_contacts.
    Scope: rename + cast + light cleanup only. No joins, no dedup, no filters,
    no business logic. Downstream models reference this model, never bronze directly.
    Raw columns are all STRING (bronze keeps data exactly as received).
    Validated against data 2026-11-18: contact_id unique, account_id always
    present, email missing on 161 rows (kept NULL — do not not_null-test it),
    mailing_state is a 2-letter USPS code, created_date/last_modified_date are
    ISO strings ('...T..:..:...+0000') that cast to timestamp, _rescued_data empty.
#}

with source as (

    select * from {{ source('bronze', 'crm_contacts') }}

),

staged as (

    select

        -- Keys & identity
        nullif(trim(contact_id), '')                    as contact_id,       -- grain of this table
        nullif(trim(account_id), '')                   as account_id,       -- CRM account key
        nullif(trim(first_name), '')                   as first_name,
        nullif(trim(last_name), '')                    as last_name,
        nullif(lower(trim(email)), '')                 as email,            -- lowercased: identity-resolution candidate; NULL on 161 rows
        nullif(trim(phone), '')                       as phone,

        -- Role & employer
        nullif(trim(title), '')                        as title,
        nullif(trim(account_name), '')                 as account_name,

        -- Mailing address
        nullif(trim(mailing_street), '')               as mailing_street,
        nullif(trim(mailing_city), '')                 as mailing_city,
        upper(nullif(trim(mailing_state), ''))          as mailing_state,    -- 2-letter USPS state code
        nullif(trim(mailing_postal_code), '')           as mailing_postal_code,  -- string on purpose: leading zeros

        -- Timestamps (ISO strings with millis + '+0000' offset in raw)
        try_cast(created_date as timestamp)            as created_at,
        try_cast(last_modified_date as timestamp)       as last_modified_at,

        -- Loader metadata passthrough (audit / row-level lineage)
        _batch_data,
        _source_file,
        _loaded_at
        -- _rescued_data intentionally dropped (empty as of 2026-11-18). If Auto
        -- Loader ever rescues a column, re-add it here so schema drift is visible.

    from source

)

select * from staged
