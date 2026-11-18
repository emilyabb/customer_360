# Landing Data Dictionary

This dictionary describes every CSV currently under `landing/` (batch 0, dated 2026-11-02). Table names use `<source_system>_<entity>`, matching the project convention. Types are inferred from the full CSV contents and field meaning; identifier fields are strings even when their values contain only digits, so leading zeros and identifier semantics are preserved.

The source systems and expected batch-0 counts follow [the project plan](PROJECT_PLAN.md). Counts below are the observed CSV row counts. Empty CSV cells are treated as null; samples show the first non-empty value in each column.

## Tables

| Table | Rows | Source file |
| --- | ---: | --- |
| `billing_customers` | 4,207 | `landing/billing/customers/batch_date=2026-11-02/customers_b0000.csv` |
| `billing_invoices` | 74,428 | `landing/billing/invoices/batch_date=2026-11-02/invoices_b0000.csv` |
| `crm_contacts` | 5,313 | `landing/crm/contacts/batch_date=2026-11-02/contacts_b0000.csv` |
| `marketing_leads` | 7,665 | `landing/marketing/leads/batch_date=2026-11-02/leads_b0000.csv` |
| `marketing_touches` | 23,542 | `landing/marketing/touches/batch_date=2026-11-02/touches_b0000.csv` |
| `support_requesters` | 2,360 | `landing/support/requesters/batch_date=2026-11-02/requesters_b0000.csv` |
| `support_tickets` | 5,549 | `landing/support/tickets/batch_date=2026-11-02/tickets_b0000.csv` |
| `answer_key_answer_key` | 19,545 | `landing/_answer_key/answer_key/batch_date=2026-11-02/answer_key_b0000.csv` |

### Natural keys and grain

The natural key of a table is the column (or columns) the source system assigns to uniquely identify one row. All keys below were validated against the batch-0 bronze data on 2026-11-18: every key is unique across its table with no null or empty values, and every cross-table reference resolves (no orphan `customer_id`, `lead_id`, or `requester_id` values).

| Table | Natural key | Grain (one row per…) |
| --- | --- | --- |
| `billing_customers` | `customer_id` | billing customer record (Stripe-style ID) |
| `billing_invoices` | `invoice_id` | invoice |
| `crm_contacts` | `contact_id` | CRM contact record (Salesforce-style ID) |
| `marketing_leads` | `lead_id` | marketing lead (HubSpot-style ID) |
| `marketing_touches` | `touch_id` | marketing touch event |
| `support_requesters` | `requester_id` | support requester record (Zendesk-style ID) |
| `support_tickets` | `ticket_id` | support ticket |
| `answer_key_answer_key` | `source_system` + `source_table` + `source_record_id` (composite) | source record mapped to its ground-truth customer |

These keys identify source records, not unique real-world people or companies: the same person can appear under multiple IDs across and within systems (duplicate CRM contacts, up to 3 leads per person, work and personal inboxes in support), which is exactly what the identity-resolution phase is built to resolve. See the per-table notes below for validation counts and caveats.

## Column details

### `billing_customers`

Billing customers.

**Natural key:** `customer_id` — one row per billing customer record. Validated 2026-11-18: 4,207 rows = 4,207 distinct IDs, no nulls or empty values. Caveat: the 2025-03-01 billing migration re-created some customers instead of mapping them, so one real-world customer can hold two billing `customer_id`s with revenue split across both.

| Field name | Data type | Sample value |
| --- | --- | --- |
| `customer_id` | `STRING` | `cus_J9M95myBAeB3yU` |
| `name` | `STRING` | `Jon Ruiz` |
| `email` | `STRING` | `jonathan.ruiz@fergusonhealth.net` |
| `phone` | `STRING` | `(441) 925-5641` |
| `company_name` | `STRING` | `Ferguson Health LLC` |
| `address_line1` | `STRING` | `0607 Mcmahon Pass` |
| `address_line2` | `STRING` | `Attn: Accounts Payable` |
| `city` | `STRING` | `New Jacob` |
| `state` | `STRING` | `DC` |
| `postal_code` | `STRING` | `20031-2594` |
| `currency` | `STRING` | `usd` |
| `created` | `BIGINT (Unix epoch seconds)` | `1780168385` |

### `billing_invoices`

Billing invoices.

**Natural key:** `invoice_id` — one row per invoice. Validated 2026-11-18: 74,428 rows = 74,428 distinct IDs, no nulls or empty values. `customer_id` is a foreign key to `billing_customers`; all 4,206 distinct values resolve (no orphans).

| Field name | Data type | Sample value |
| --- | --- | --- |
| `invoice_id` | `STRING` | `in_r8KzcG9uFe519N` |
| `customer_id` | `STRING` | `cus_J9M95myBAeB3yU` |
| `invoice_date` | `DATE` | `2026-05-28` |
| `amount_due` | `DECIMAL(12,2)` | `1378.37` |
| `currency` | `STRING` | `usd` |
| `status` | `STRING` | `paid` |

### `crm_contacts`

CRM contacts.

**Natural key:** `contact_id` — one row per CRM contact record. Validated 2026-11-18: 5,313 rows = 5,313 distinct IDs, no nulls or empty values. Caveat: ~8% of contacts are duplicates in the source, so the same person can appear under multiple `contact_id`s (sometimes under a duplicate account); `account_id` groups contacts by account, not by person.

| Field name | Data type | Sample value |
| --- | --- | --- |
| `contact_id` | `STRING` | `003tXwzBefpKUHuTtS` |
| `account_id` | `STRING` | `0013NrGFS0YPB9lD6u` |
| `first_name` | `STRING` | `Edward` |
| `last_name` | `STRING` | `Coffey` |
| `title` | `STRING` | `IT Director` |
| `account_name` | `STRING` | `Moore Media Group` |
| `email` | `STRING` | `edward.coffey@mooremedia.io` |
| `phone` | `STRING` | `(673) 538-4583` |
| `mailing_street` | `STRING` | `6463 Carroll Pine` |
| `mailing_city` | `STRING` | `Martinton` |
| `mailing_state` | `STRING` | `ID` |
| `mailing_postal_code` | `STRING` | `83662` |
| `created_date` | `TIMESTAMP (UTC offset in source)` | `2024-07-24T23:26:57.000+0000` |
| `last_modified_date` | `TIMESTAMP (UTC offset in source)` | `2024-07-24T23:26:57.000+0000` |

### `marketing_leads`

Marketing leads.

**Natural key:** `lead_id` — one row per marketing lead. Validated 2026-11-18: 7,665 rows = 7,665 distinct IDs, no nulls or empty values. Caveat: the same person can have up to 3 leads with different emails (Gmail dots, `+tags`, `.con` typos), so `lead_id` — not email or person — is the unique identifier at this grain.

| Field name | Data type | Sample value |
| --- | --- | --- |
| `lead_id` | `STRING` | `726493684` |
| `firstname` | `STRING` | `Eddie` |
| `lastname` | `STRING` | `Coffey` |
| `email` | `STRING` | `edward.coffey+news@gmail.con` |
| `company` | `STRING` | `Moore Media Group` |
| `phone` | `STRING` | `673.538.4583` |
| `lifecyclestage` | `STRING` | `opportunity` |
| `lead_source` | `STRING` | `Paid Social` |
| `createdate` | `TIMESTAMP (UTC)` | `2023-11-28T16:45:57Z` |
| `lastmodifieddate` | `TIMESTAMP (UTC)` | `2023-12-14T16:45:57Z` |

### `marketing_touches`

Marketing touches.

**Natural key:** `touch_id` — one row per marketing touch event. Validated 2026-11-18: 23,542 rows = 23,542 distinct IDs, no nulls or empty values. `lead_id` is a foreign key to `marketing_leads`; all 7,566 distinct values resolve (no orphans).

| Field name | Data type | Sample value |
| --- | --- | --- |
| `touch_id` | `STRING` | `6640342949` |
| `lead_id` | `STRING` | `726493684` |
| `touch_type` | `STRING` | `email_open` |
| `campaign` | `STRING` | `Year-End Webinar` |
| `touch_ts` | `TIMESTAMP (UTC)` | `2023-12-17T15:39:54Z` |

### `support_requesters`

Support requesters.

**Natural key:** `requester_id` — one row per support requester record. Validated 2026-11-18: 2,360 rows = 2,360 distinct IDs, no nulls or empty values. Caveat: the same person can appear as multiple requesters (work and personal inboxes), and the single `name` field mixes formats, so requester ID is not a person key.

| Field name | Data type | Sample value |
| --- | --- | --- |
| `requester_id` | `STRING` | `9079057997` |
| `name` | `STRING` | `Deenise Todd` |
| `email` | `STRING` | `dtodd78@gmail.con` |
| `phone` | `STRING` | `1-507-825-9861` |
| `organization` | `STRING` | `Rodriguez Analytics Corp.` |
| `created_at` | `TIMESTAMP (UTC)` | `2025-09-29T07:50:31Z` |

### `support_tickets`

Support tickets.

**Natural key:** `ticket_id` — one row per support ticket. Validated 2026-11-18: 5,549 rows = 5,549 distinct IDs, no nulls or empty values. `requester_id` is a foreign key to `support_requesters`; all 2,360 distinct values resolve (no orphans).

| Field name | Data type | Sample value |
| --- | --- | --- |
| `ticket_id` | `STRING` | `600553082` |
| `requester_id` | `STRING` | `9079057997` |
| `subject` | `STRING` | `Feature request` |
| `priority` | `STRING` | `low` |
| `channel` | `STRING` | `chat` |
| `status` | `STRING` | `solved` |
| `created_at` | `TIMESTAMP (UTC)` | `2025-09-29T07:50:31Z` |
| `solved_at` | `TIMESTAMP (UTC)` | `2025-09-29T23:36:30Z` |

### `answer_key_answer_key`

Answer key (evaluation only). Ground-truth labels are for evaluation only and must not be loaded into operational bronze tables. As of 2026-11-18 the Auto Loader ingests it into `c360.evaluation_dev.answer_key` — its own schema, outside the bronze→silver→gold modeling path — so the identity-resolution models cannot read `true_customer_id`. dbt reaches it only through the `evaluation` source, and only the Phase-2 `match_evaluation` model joins it.

**Natural key:** `source_system` + `source_table` + `source_record_id` (composite) — one row per source record. Validated 2026-11-18: 19,545 rows = 19,545 distinct key combinations, no null or empty `source_record_id` values. `true_customer_id` is not unique by design: many source records map to the same ground-truth customer.

| Field name | Data type | Sample value |
| --- | --- | --- |
| `source_system` | `STRING` | `crm` |
| `source_table` | `STRING` | `contacts` |
| `source_record_id` | `STRING` | `003tXwzBefpKUHuTtS` |
| `true_customer_id` | `STRING` | `TC-000000` |

## Type and source notes

- `STRING` is used for source and foreign keys, including numeric-looking IDs such as `lead_id`, `ticket_id`, and `requester_id`.
- Postal codes, phone numbers, currency codes, status values, and other categorical/text fields are strings.
- `billing_customers.created` is an integer Unix epoch timestamp in seconds.
- ISO-formatted date and timestamp strings are represented as `DATE` or `TIMESTAMP`; UTC markers or offsets are present in the source for timestamps.
- `billing_invoices.amount_due` is represented as `DECIMAL(12,2)` for currency precision.
- The project plan lists billing customers and invoices as separate row counts; both are included above. The answer key is documented because it is present in the landing directory; per the project plan it is ground truth for scoring and stays out of bronze — it loads into `c360.evaluation_dev.answer_key`, never `c360.bronze_dev` (implemented 2026-11-18).
