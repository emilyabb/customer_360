# Databricks notebook source
# MAGIC %md
# MAGIC # Land one Customer 360 batch in a Unity Catalog volume
# MAGIC
# MAGIC Writes CSVs for the four source systems plus the answer key to
# MAGIC `/Volumes/<catalog>/<schema>/<volume>/`. Bronze ingestion (Auto Loader) is your job in Phase 1.
# MAGIC
# MAGIC **Setup:** keep this notebook and `c360_generator.py` in the same folder of your Git folder.
# MAGIC Run batch 0 once for the full history, then batch 1, 2, 3... for each daily increment.
# MAGIC In Phase 4, Airflow passes `batch` as a notebook parameter.

# COMMAND ----------

# MAGIC %pip install "faker>=28,<40"

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text("catalog", "c360")
dbutils.widgets.text("schema", "landing")
dbutils.widgets.text("volume", "raw")
dbutils.widgets.text("start_date", "2026-11-02")
dbutils.widgets.text("batch", "0")
dbutils.widgets.text("n_customers", "7000")
dbutils.widgets.text("seed", "42")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
volume = dbutils.widgets.get("volume")
batch = int(dbutils.widgets.get("batch"))
n_customers = int(dbutils.widgets.get("n_customers"))
seed = int(dbutils.widgets.get("seed"))

from datetime import date

start_date = date.fromisoformat(dbutils.widgets.get("start_date"))

# COMMAND ----------

existing = {row[0] for row in spark.sql("SHOW CATALOGS").collect()}
if catalog not in existing:
    try:
        spark.sql(f"CREATE CATALOG IF NOT EXISTS `{catalog}`")
    except Exception as err:
        raise RuntimeError(
            f"Couldn't create catalog `{catalog}`. If your workspace won't let you create catalogs, "
            "set the catalog widget to `workspace` (the Free Edition default) and rerun."
        ) from err

spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{catalog}`.`{schema}`")
spark.sql(f"CREATE VOLUME IF NOT EXISTS `{catalog}`.`{schema}`.`{volume}`")
landing_root = f"/Volumes/{catalog}/{schema}/{volume}"

# COMMAND ----------

import os
import sys

sys.path.insert(0, os.getcwd())  # c360_generator.py sits next to this notebook
import c360_generator as gen

written = gen.write_batch(landing_root, batch=batch, start=start_date, n_customers=n_customers, seed=seed)
display(spark.createDataFrame(written))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Smoke test
# MAGIC Row counts per source folder across every batch landed so far. Spark skips `_answer_key`
# MAGIC because the folder starts with an underscore, so point a separate read at it when you score matches.

# COMMAND ----------

from pyspark.sql import functions as F

for name, (system, entity, _) in gen.TABLES.items():
    if system.startswith("_"):
        continue
    df = spark.read.option("header", True).csv(f"{landing_root}/{system}/{entity}/")
    print(f"{name:<20} {df.count():>8,} rows across {df.select('batch_date').distinct().count()} batch(es)")

answer_key = spark.read.option("header", True).csv(f"{landing_root}/_answer_key/answer_key/")
display(answer_key.groupBy("source_system").agg(F.count("*").alias("records"), F.countDistinct("true_customer_id").alias("true_customers")))
