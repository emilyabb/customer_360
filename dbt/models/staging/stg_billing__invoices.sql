{{ config(materialized='view') }}

{#
    Staging model — one per source table, 1:1 with c360.bronze_dev.billing_invoices.
    Scope: rename + cast + light cleanup only. No joins, no dedup, no filters,
    no business logic. Downstream models reference this model, never bronze directly.
    Raw columns are all STRING (bronze keeps data exactly as received).
    Validated against data 2026-11-18: invoice_id unique, no missing
    ids/dates/amounts, invoice_date is ISO 'YYYY-MM-DD', amount_due always
    parses as decimal, currency always 'usd', status in
    {open, void, paid, uncollectible}, _rescued_data empty.
#}

with source as (

    select * from {{ source('bronze', 'billing_invoices') }}

),

staged as (

    select

        -- Keys
        nullif(trim(invoice_id), '')                   as invoice_id,       -- 'in_*' key; grain of this table
        nullif(trim(customer_id), '')                  as customer_id,      -- FK → stg_billing__customers

        -- Invoice facts
        try_cast(invoice_date as date)                 as invoice_date,     -- ISO date string 'YYYY-MM-DD'
        try_cast(amount_due as decimal(12,2))          as amount_due,       -- numeric string in raw
        upper(nullif(trim(currency), ''))              as currency,         -- raw is lowercase ('usd')
        nullif(trim(status), '')                       as status,           -- raw casing: open | void | paid | uncollectible

        -- Loader metadata passthrough (audit / row-level lineage)
        _batch_data,
        _source_file,
        _loaded_at
        -- _rescued_data intentionally dropped (empty as of 2026-11-18). If Auto
        -- Loader ever rescues a column, re-add it here so schema drift is visible.

    from source

)

select * from staged
