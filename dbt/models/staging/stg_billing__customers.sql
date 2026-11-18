{{ config(materialized='view') }}

{#
    Staging model — one per source table, 1:1 with c360.bronze_dev.billing_customers.
    Scope: rename + cast + light cleanup only. No joins, no dedup, no filters,
    no business logic. Downstream models reference this model, never bronze directly.
    Raw columns are all STRING (bronze keeps data exactly as received).
    Validated against data 2026-11-15: customer_id unique (4,207 = 4,207 distinct),
    no missing ids/emails, `created` is epoch seconds, currency always 'usd',
    _rescued_data empty.
#}

with source as (

    select * from {{ source('bronze', 'billing_customers') }}

),

staged as (

    select

        -- Keys & identity
        nullif(trim(customer_id), '')                  as customer_id,       -- 'cus_*' key; grain of this table
        nullif(trim(name), '')                         as name,
        nullif(lower(trim(email)), '')                 as email,             -- lowercased: identity-resolution candidate
        nullif(trim(phone), '')                        as phone,

        -- Company & address
        nullif(trim(company_name), '')                 as company_name,
        nullif(trim(address_line1), '')                as address_line1,
        nullif(trim(address_line2), '')                as address_line2,
        nullif(trim(city), '')                         as city,
        upper(nullif(trim(state), ''))                 as state,
        nullif(trim(postal_code), '')                  as postal_code,      -- string on purpose: leading zeros + ZIP+4

        -- Codes & timestamps
        upper(nullif(trim(currency), ''))              as currency,         -- raw is lowercase ('usd')
        timestamp_seconds(try_cast(created as bigint)) as created_at,       -- epoch seconds stored as STRING

        -- Loader metadata passthrough (audit / row-level lineage)
        _batch_data,
        _source_file,
        _loaded_at
        -- _rescued_data intentionally dropped (empty as of 2026-11-15). If Auto
        -- Loader ever rescues a column, re-add it here so schema drift is visible.

    from source

)

select * from staged
