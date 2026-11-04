# Customer 360 generator

## Local development

The repository root uses `uv` to manage the laptop development environment. Install `uv`, then run these commands from the repository root:

```powershell
uv sync
uv run python generator/c360_generator.py --out ./landing --batch 0
```

`uv.lock` pins the resolved versions for repeatable local runs. To run the Snowflake stage uploader from your laptop, install its optional connector dependency:

```powershell
uv sync --extra snowflake
uv run python generator/snowflake_land_batch.py --batch 0
```

## Databricks and Snowflake environments

The `uv` environment is for local development; Databricks and Snowflake do not need to use it. Install Faker through each platform's own job, notebook, or Snowpark dependency settings. The Databricks notebook installs Faker in its notebook environment. The Snowflake uploader in this folder is a laptop-side client that uses the Snowflake connector to upload generated CSVs to a stage.

