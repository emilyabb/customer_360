-- validate_natural_keys.sql
-- Due-diligence checks for the Customer 360 bronze layer (c360.bronze_dev).
--
-- Purpose: prove the natural-key and foreign-key claims documented in
-- docs/DATA_DICTIONARY.md ("Natural keys and grain" section) against real data.
--
-- How to run: any SQL warehouse or serverless compute (plain Spark SQL, no
-- temp views or Python needed). Run after each new batch lands in bronze so
-- the claims stay true as the data grows.
--
-- Sections:
--   1. Natural key uniqueness — one row per table, verdict VALID when
--      distinct keys = row count and no null/empty key values.
--   2. Foreign keys — orphan counts per relationship; 0 = all values resolve.
--   3. Assertion view — returns ONLY failing checks; an empty result means
--      every validation passed.
--
-- First run: 2026-11-18, batch 0 (2026-11-02). All checks passed:
--   billing_customers   customer_id        4,207 = 4,207 distinct
--   billing_invoices    invoice_id        74,428 = 74,428 distinct
--   crm_contacts        contact_id         5,313 = 5,313 distinct
--   marketing_leads     lead_id            7,665 = 7,665 distinct
--   marketing_touches   touch_id          23,542 = 23,542 distinct
--   support_requesters  requester_id        2,360 = 2,360 distinct
--   support_tickets     ticket_id           5,549 = 5,549 distinct
--   answer_key          (source_system, source_table, source_record_id)
--                                        19,545 = 19,545 distinct
--   FK orphans: invoices→customers 0, touches→leads 0, tickets→requesters 0

-- ======================================================================
-- 1. Natural key uniqueness and completeness (per table)
-- =====================================================================

CREATE OR REPLACE TEMP VIEW key_checks AS
SELECT 'billing_customers' AS table_name, 'customer_id' AS natural_key,
       COUNT(*) AS n_rows,
       COUNT(DISTINCT customer_id) AS n_distinct_keys,
       SUM(CASE WHEN customer_id IS NULL OR trim(customer_id) = '' THEN 1 ELSE 0 END) AS n_bad_keys
FROM c360.bronze_dev.billing_customers
UNION ALL
SELECT 'billing_invoices', 'invoice_id', COUNT(*),
       COUNT(DISTINCT invoice_id),
       SUM(CASE WHEN invoice_id IS NULL OR trim(invoice_id) = '' THEN 1 ELSE 0 END)
FROM c360.bronze_dev.billing_invoices
UNION ALL
SELECT 'crm_contacts', 'contact_id', COUNT(*),
       COUNT(DISTINCT contact_id),
       SUM(CASE WHEN contact_id IS NULL OR trim(contact_id) = '' THEN 1 ELSE 0 END)
FROM c360.bronze_dev.crm_contacts
UNION ALL
SELECT 'marketing_leads', 'lead_id', COUNT(*),
       COUNT(DISTINCT lead_id),
       SUM(CASE WHEN lead_id IS NULL OR trim(lead_id) = '' THEN 1 ELSE 0 END)
FROM c360.bronze_dev.marketing_leads
UNION ALL
SELECT 'marketing_touches', 'touch_id', COUNT(*),
       COUNT(DISTINCT touch_id),
       SUM(CASE WHEN touch_id IS NULL OR trim(touch_id) = '' THEN 1 ELSE 0 END)
FROM c360.bronze_dev.marketing_touches
UNION ALL
SELECT 'support_requesters', 'requester_id', COUNT(*),
       COUNT(DISTINCT requester_id),
       SUM(CASE WHEN requester_id IS NULL OR trim(requester_id) = '' THEN 1 ELSE 0 END)
FROM c360.bronze_dev.support_requesters
UNION ALL
SELECT 'support_tickets', 'ticket_id', COUNT(*),
       COUNT(DISTINCT ticket_id),
       SUM(CASE WHEN ticket_id IS NULL OR trim(ticket_id) = '' THEN 1 ELSE 0 END)
FROM c360.bronze_dev.support_tickets
UNION ALL
SELECT 'answer_key', 'source_system + source_table + source_record_id', COUNT(*),
       COUNT(DISTINCT concat_ws('|', source_system, source_table, source_record_id)),
       SUM(CASE WHEN source_record_id IS NULL OR trim(source_record_id) = '' THEN 1 ELSE 0 END)
FROM c360.bronze_dev.answer_key;

SELECT table_name, natural_key, n_rows, n_distinct_keys, n_bad_keys,
       CASE WHEN n_rows = n_distinct_keys AND n_bad_keys = 0 THEN 'VALID' ELSE 'FAIL' END AS verdict
FROM key_checks
ORDER BY table_name;

-- ======================================================================
-- 2. Foreign-key integrity (orphans; 0 = every value resolves)
-- ======================================================================

CREATE OR REPLACE TEMP VIEW fk_checks AS
SELECT 'billing_invoices.customer_id -> billing_customers.customer_id' AS relationship,
       COUNT(DISTINCT i.customer_id) AS n_distinct_fk_values,
       COUNT(DISTINCT CASE WHEN c.customer_id IS NULL THEN i.customer_id END) AS n_orphan_values
FROM c360.bronze_dev.billing_invoices i
LEFT JOIN c360.bronze_dev.billing_customers c ON i.customer_id = c.customer_id
UNION ALL
SELECT 'marketing_touches.lead_id -> marketing_leads.lead_id',
       COUNT(DISTINCT t.lead_id),
       COUNT(DISTINCT CASE WHEN l.lead_id IS NULL THEN t.lead_id END)
FROM c360.bronze_dev.marketing_touches t
LEFT JOIN c360.bronze_dev.marketing_leads l ON t.lead_id = l.lead_id
UNION ALL
SELECT 'support_tickets.requester_id -> support_requesters.requester_id',
       COUNT(DISTINCT k.requester_id),
       COUNT(DISTINCT CASE WHEN r.requester_id IS NULL THEN k.requester_id END)
FROM c360.bronze_dev.support_tickets k
LEFT JOIN c360.bronze_dev.support_requesters r ON k.requester_id = r.requester_id;

SELECT relationship, n_distinct_fk_values, n_orphan_values,
       CASE WHEN n_orphan_values = 0 THEN 'VALID' ELSE 'FAIL' END AS verdict
FROM fk_checks
ORDER BY relationship;

-- ======================================================================
-- 3. Assertion: returns ONLY failing checks.
--    Empty result = every natural key and foreign key validated.
-- ======================================================================

SELECT table_name AS failing_check, natural_key, n_rows, n_distinct_keys, n_bad_keys, 'duplicate or missing key' AS reason
FROM key_checks
WHERE n_rows <> n_distinct_keys OR n_bad_keys > 0
UNION ALL
SELECT relationship, 'foreign key', n_distinct_fk_values, n_orphan_values, NULL, 'orphan values found' AS reason
FROM fk_checks
WHERE n_orphan_values > 0;
