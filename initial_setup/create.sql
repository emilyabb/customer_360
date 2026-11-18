-- Customer 360 initial setup
-- Creates the c360 catalog and its medallion-layer schemas for the dev environment.

CREATE CATALOG IF NOT EXISTS c360
  COMMENT 'Customer 360 project catalog';

CREATE SCHEMA IF NOT EXISTS c360.landing
  COMMENT 'Landing zone: raw files as received, no transformation';

CREATE SCHEMA IF NOT EXISTS c360.bronze_dev
  COMMENT 'Bronze layer: raw ingested data';

CREATE SCHEMA IF NOT EXISTS c360.silver_dev
  COMMENT 'Silver layer: cleaned, validated, deduplicated data';

CREATE SCHEMA IF NOT EXISTS c360.gold_dev
  COMMENT 'Gold layer: curated business-level tables';

-- Evaluation layer for the identity-resolution answer key (source record →
-- true_customer_id ground truth). Deliberately outside the bronze→silver→gold
-- modeling path (PROJECT_PLAN.md Phase 1: "keep the true_customer_id answer key
-- out of bronze") so matching models cannot read true_customer_id; it is only
-- joined by the Phase-2 match_evaluation dbt model.
CREATE SCHEMA IF NOT EXISTS c360.evaluation_dev
  COMMENT 'Evaluation layer: answer key ground truth, outside the modeling pipeline';

CREATE VOLUME IF NOT EXISTS c360.landing.raw
  COMMENT 'Landing zone raw file storage: source files as received';