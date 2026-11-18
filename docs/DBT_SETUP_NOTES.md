# dbt Setup Notes — Customer 360

Working notes from setting up the dbt project in this repo (repo root: `/Repos/dev/customer_360`, dbt project: `dbt/`). History is preserved as written; see the "Update — Nov 18 2026" section at the bottom for what has changed since.

## Project layout

* `dbt/dbt_project.yml` — declares profile `customer_360_dbt`
* `dbt/models/sources.yml` — source definitions (below)
* `dbt/profiles.yml` — connection profile (gitignored, holds a token)
* Bronze source data: Unity Catalog `c360.bronze_dev` (8 tables, ingested by the Auto Loader notebook)

## sources.yml — outline

Lives at `dbt/models/sources.yml` (dbt auto-discovers YAML under model-paths).

* `version: 2`
* `sources:` is a **list** — each source needs `- name:` (a missing dash/indent breaks parsing; this bit us once)
  * `name: bronze` — short handle used in `{{ source('bronze', '<table>') }}` refs
  * `database: c360` — dbt-databricks maps `database` to the UC catalog
  * `schema: bronze_dev` — second-level namespace; `_dev` suffix is intentional for now
  * `tables:` — must match the real `c360.bronze_dev.*` table names exactly:
    * billing_customers, billing_invoices, crm_contacts, marketing_leads,
      marketing_touches, support_requesters, support_tickets, answer_key
* Freshness config added (Nov 10): source-level `config:` block with `loaded_at_field: _loaded_at`, `warn_after: 24h`, `error_after: 48h` — dbt ≥ 1.10 requires these under `config:`, not as top-level source properties (that emits a PropertyMovedToConfigDeprecation warning). Applies to all 8 tables at once; `dbt source freshness` will now work.
* Reference in models as `{{ source('bronze', 'billing_customers') }}` — gives lineage and rename protection instead of hardcoding `c360.bronze_dev.*`

## profiles.yml — status

Lives at the **dbt project root** (`dbt/profiles.yml`) — a deliberate, non-default choice:

* dbt's default lookup is `~/.dbt/profiles.yml` on the machine running dbt, NOT the project directory
* Because it's in the project, every command must run from `dbt/` with `DBT_PROFILES_DIR=. dbt <command>` (or `--profiles-dir .`)
* Top-level key `customer_360_dbt` must match `profile:` in dbt_project.yml exactly
* Contents so far:
  * `type: databricks` adapter, `target: dev`
  * `http_path: /sql/1.0/warehouses/0008013c8b90dc49` (Serverless Starter Warehouse — auto-starts on connect)
  * `schema: silver_dev` — default schema where dbt *builds* models (separate from the bronze_dev source schema)
  * `threads: 4`
* **Done (Nov 10 2026):** both placeholders filled in — `host` = dbc-61c13420-8917.cloud.databricks.com (bare hostname; dbt rejects an `https://` scheme or trailing slash) and a personal access token (scope `sql`, via User Settings → Developer → Access tokens). Token is never recorded in these notes.
* **Never commit this file** — it's in `.gitignore` at the repo root

## Where dbt runs / validating

dbt is not pre-installed on Databricks compute. Two options:

1. **Locally (recommended, matches our branch workflow):** clone the repo on your PC, `pip install dbt-databricks` in a venv, then from `dbt/`: `DBT_PROFILES_DIR=. dbt parse`. Caveat: `profiles.yml` is gitignored, so the local clone won't have it — copy it over manually (or recreate it in `~/.dbt/` on the PC).
2. **In a Databricks notebook (serverless):** `%pip install dbt-databricks`, then shell into the repo path under `/Workspace/Repos/...` and run `DBT_PROFILES_DIR=. dbt parse`.

A successful parse validates profiles.yml and sources.yml together; a "relation not found" error at compile time means a source table name is misspelled.

## The dbt job (Lakeflow) — what exists vs. what's next

A dbt job already exists in the workspace, created by clicking through the Jobs UI on **Nov 5 2026**:

* Job: **"Customer 360 dbt"** (id 425973960094643; renamed from "New Job 2026-11-05 22:23:50"), task key `c360_dbt_task`
* Task type: dbt, source `WORKSPACE`, project directory `/Repos/dev/customer_360/dbt`
* Commands: `["dbt debug"]` — a connection/config validation only, no models existed yet
* Connection: catalog `c360`, schema **`silver_dev`** (retargeted from the stale `silver` on Nov 10 2026), warehouse `0008013c8b90dc49` (same Serverless Starter Warehouse as profiles.yml)
* Run history (Nov 5): 3 runs SUCCESS, 1 cancelled by user

**Key mechanic:** a job's dbt task does NOT read `profiles.yml` — Databricks generates the connection profile from the task settings (warehouse_id + catalog + schema). The job and the profiles.yml are independent paths to the same project:

| | Job task | profiles.yml |
| --- | --- | --- |
| Trigger | UI / schedule | manual CLI / notebook |
| Profile source | task settings | `dbt/profiles.yml` |
| Use case | scheduled runs | local dev & ad-hoc validation |

**What the job did on Nov 5 (already done):** validated the project connection via `dbt debug`, against the pre-rename schema `silver`.

**What we did on Nov 10 (done):**

1. ✅ Retargeted the task's schema from `silver` to `silver_dev` — the job predated the Nov 10 schema rename (`*_dev`), so as-is it would have materialized into the stale `c360.silver`.
2. ✅ Renamed the job to **"Customer 360 dbt"** (was "New Job 2026-11-05 22:23:50").
3. ✅ Verified with a fresh run (run 300500393131364): SUCCESS in ~46s, `dbt debug` against schema `silver_dev`.
4. Longer term (not done): extend commands beyond `dbt debug` to `dbt build` once the first models exist, and put the job on a schedule.

## Git hygiene

`.gitignore` (repo root) ignores only `dbt/profiles.yml` — it holds an access token and must never be committed. `docs/DBT_SETUP_NOTES.md` (this file) is intentionally tracked in git so the setup history travels with the repo. (Moved from `dbt/docs/` to `docs/` on Nov 18 2026 to consolidate all project docs in one place; git will see this as a rename.)

## Update — Nov 18 2026 (answer key out of bronze)

* The answer key is no longer a bronze table: per PROJECT_PLAN.md Phase 1 it now lives in `c360.evaluation_dev.answer_key` (own schema, ingested there by the Auto Loader, outside the bronze→silver→gold modeling path). `sources.yml` therefore declares **7 bronze tables** plus a second source `evaluation` → `c360.evaluation_dev.answer_key` (no freshness config); the "8 tables / answer_key in bronze" statements above are historical.
* The 7 staging models (`stg_<source>__<entity>`) and their tests are complete, and the job command is now `dbt build` (no selector). See `docs/DATA_DICTIONARY.md` and `docs/PROJECT_PLAN.md` for current state.
