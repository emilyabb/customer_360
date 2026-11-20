# dbt setup on Databricks

This guide configures the `dbt/` project in the Customer 360 Git folder and runs dbt Core through the Databricks UI. It does not require a local Python environment or `uv`. Local development can be added later.

## Project layout

The repository already has a `dbt/` directory. Keep `dbt_project.yml` at the root of that directory, with model property files under `models/`:

```text
dbt/
├── dbt_project.yml
└── models/
    └── sources.yml
```

Create `dbt/dbt_project.yml` with this minimal configuration:

```yaml
name: customer_360_dbt
version: "1.0.0"
config-version: 2
profile: customer_360_dbt
model-paths: ["models"]
```

The `profile` name identifies the connection profile dbt uses. For a Databricks dbt task configured with a SQL warehouse in the UI, Databricks supplies the run-time profile and credentials; do not commit a token or generated `profiles.yml` to the repository.

## Configure the Databricks job

In the Databricks workspace:

1. Open **Jobs & Pipelines** and create or edit the Customer 360 dbt job.
2. Add a task of type **dbt**.
3. Set **Source** to **Workspace** and select the Git-folder project directory, for example `/Repos/dev/customer_360/dbt`. This directory must contain `dbt_project.yml`.
4. Select the Free Edition SQL warehouse. The warehouse runs SQL compiled by dbt; **dbt CLI compute** runs the dbt process. Use **Serverless** for CLI compute and the `dbt-default` environment when available.
5. Set **Warehouse catalog** to `c360`.
6. Set **Warehouse schema** to the intended dbt output schema. The successful connection recorded for this workspace reported `c360.silver`. Use `silver_dev` instead only if that is the output schema actually created in the workspace.
7. For the first run, use only this command:

   ```text
   dbt debug
   ```

8. Save the task and click **Run now**. In the run output, confirm the project and profile checks pass and the connection test reports success.

The UI-created dbt task obtains a short-lived token for its **Run as** identity. That identity needs permission to use the SQL warehouse and access the catalog, schemas, and source tables used by the project. It will also need permission to create tables or views in the output schema when dbt models are added.

## Declare bronze sources and freshness

Before configuring freshness, use **Catalog Explorer** to confirm:

- The actual source schema in `c360` (`bronze` or `bronze_dev`, depending on the schema created in this workspace).
- The exact table names that Auto Loader created.
- Each table has a populated timestamp column named `_loaded_at`.

`_loaded_at` should record when a row was ingested into bronze. It is the freshness timestamp; business event dates such as invoice date are not substitutes for ingestion time.

Create `dbt/models/sources.yml`. This example uses the seven operational source tables from the generated dataset and intentionally excludes the answer key. Adjust the schema or table names to match Catalog Explorer:

```yaml
version: 2

sources:
  - name: bronze
    database: c360
    schema: bronze
    config:
      loaded_at_field: _loaded_at
      freshness:
        warn_after: {count: 24, period: hour}
        error_after: {count: 48, period: hour}
    tables:
      - name: crm_contacts
      - name: billing_customers
      - name: billing_invoices
      - name: marketing_leads
      - name: marketing_touches
      - name: support_requesters
      - name: support_tickets
```

The example warns when the newest ingestion is over 24 hours old and errors when it is over 48 hours old. These thresholds assume daily ingestion; change them to match the intended batch schedule. If the bronze schema is `bronze_dev`, set `schema: bronze_dev` instead.

Run the freshness check by changing the dbt task command to:

```text
dbt source freshness
```

The run should report a result for each declared source table. A missing-table or missing-column error usually means the names in `sources.yml` do not match the objects in Catalog Explorer, or Auto Loader has not created/populated them yet.

## Phase 1 follow-up

Once freshness checks pass, add one staging model per source and key tests (`unique` and `not_null`) for each source key. Keep those models in the silver output schema. Do not add the answer key as an operational source; reserve it for later match-quality evaluation.

## References

- [Databricks dbt task for Lakeflow Jobs](https://docs.databricks.com/aws/en/jobs/tasks/dbt)
- [Databricks: Connect to dbt Core](https://docs.databricks.com/aws/en/partners/prep/dbt)
- [dbt source freshness configuration](https://docs.getdbt.com/reference/resource-configs/freshness)
- [dbt sources](https://docs.getdbt.com/docs/build/sources)
