"""Land one Customer 360 batch in a Snowflake internal stage.

Generates the same files as the Databricks notebook (same seed, same rows), then
PUTs them to @<database>.<schema>.<stage>/<system>/<entity>/batch_date=YYYY-MM-DD/.
Loading them into bronze with COPY INTO is your job in Phase 5.

Run from your laptop:

    pip install "faker>=28,<40" "snowflake-connector-python>=3.12"

    # PowerShell
    $env:SNOWFLAKE_ACCOUNT = "<orgname>-<accountname>"
    $env:SNOWFLAKE_USER = "<your user>"
    python snowflake_land_batch.py --batch 0

Auth defaults to externalbrowser (a browser window opens for sign-in, MFA
included). Set SNOWFLAKE_AUTHENTICATOR and SNOWFLAKE_PASSWORD to use something else.
Optional: SNOWFLAKE_ROLE, SNOWFLAKE_WAREHOUSE (PUT itself doesn't need a warehouse).
"""

from __future__ import annotations

import argparse
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

import snowflake.connector

import c360_generator as gen


def connect():
    params = {
        "account": os.environ["SNOWFLAKE_ACCOUNT"],
        "user": os.environ["SNOWFLAKE_USER"],
        "authenticator": os.environ.get("SNOWFLAKE_AUTHENTICATOR", "externalbrowser"),
    }
    for key in ("password", "role", "warehouse"):
        value = os.environ.get(f"SNOWFLAKE_{key.upper()}")
        if value:
            params[key] = value
    return snowflake.connector.connect(**params)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate one Customer 360 batch and PUT it to a Snowflake stage.")
    parser.add_argument("--database", default="C360")
    parser.add_argument("--schema", default="LANDING")
    parser.add_argument("--stage", default="RAW_STAGE")
    parser.add_argument("--batch", type=int, default=0, help="0 = full history; N = start date + N days")
    parser.add_argument("--start-date", type=date.fromisoformat, default=gen.DEFAULT_START)
    parser.add_argument("--n-customers", type=int, default=7000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    db, schema = args.database, f"{args.database}.{args.schema}"
    stage = f"{schema}.{args.stage}"

    with tempfile.TemporaryDirectory() as tmp, connect() as conn, conn.cursor() as cur:
        written = gen.write_batch(tmp, args.batch, args.start_date, args.n_customers, args.seed)

        cur.execute(f"CREATE DATABASE IF NOT EXISTS {db}")
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        cur.execute(
            f"CREATE FILE FORMAT IF NOT EXISTS {schema}.CSV_WITH_HEADER "
            "TYPE = CSV SKIP_HEADER = 1 FIELD_OPTIONALLY_ENCLOSED_BY = '\"' EMPTY_FIELD_AS_NULL = TRUE"
        )
        cur.execute(f"CREATE STAGE IF NOT EXISTS {stage} FILE_FORMAT = {schema}.CSV_WITH_HEADER")

        for row in written:
            local = Path(row["path"])
            target = local.parent.relative_to(tmp).as_posix()
            # OVERWRITE keeps reruns idempotent: same batch, same file name, same contents
            cur.execute(f"PUT 'file://{local.as_posix()}' '@{stage}/{target}/' AUTO_COMPRESS = TRUE OVERWRITE = TRUE")
            print(f"{row['table']:<20} {row['rows']:>8,}  @{stage}/{target}/")

        batch_date = (args.start_date + timedelta(days=args.batch)).isoformat()
        cur.execute(f"LIST @{stage} PATTERN = '.*batch_date={batch_date}.*'")
        print(f"\n{len(cur.fetchall())} files on the stage for this batch")


if __name__ == "__main__":
    main()
