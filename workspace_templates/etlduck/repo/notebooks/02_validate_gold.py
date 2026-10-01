# Databricks notebook source
# MAGIC %md
# MAGIC # Validate gold against silver
# MAGIC
# MAGIC Run after a pipeline run, or when a number in a dashboard looks wrong. This is the
# MAGIC notebook to open first, because it answers the question that decides where to look
# MAGIC next: **do gold and silver agree?**
# MAGIC
# MAGIC If they do, the rollup is faithful and the problem is upstream of it -- parsing,
# MAGIC quarantine, or the delivery itself. If they do not, the rollup is multiplying or losing
# MAGIC rows and nothing else matters until that is fixed.
# MAGIC
# MAGIC Uses the Spark-shaped façade over DuckDB; there is no cluster.

# COMMAND ----------

from etlduck import quality
from etlduck.spark_compat import LocalSession

session = LocalSession.builder().appName("validate-gold").getOrCreate()
print(f"session: {session.app_name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## The reconciliation
# MAGIC
# MAGIC Compared as integers, so there is no tolerance and none is needed. Money is stored as
# MAGIC a count of cents precisely so this comparison can be exact.

silver = session.sql(
    "SELECT count(*) AS rows, coalesce(sum(quantity), 0) AS quantity, "
    "coalesce(sum(amount_cents), 0) AS amount_cents FROM silver_usage"
).first()
gold = session.sql(
    "SELECT coalesce(sum(events), 0) AS rows, coalesce(sum(quantity), 0) AS quantity, "
    "coalesce(sum(amount_cents), 0) AS amount_cents FROM gold_daily_usage"
).first()

print(f"{'':14}{'silver':>14}{'gold':>14}{'':>8}")
for key in ("rows", "quantity", "amount_cents"):
    mark = "ok" if silver[key] == gold[key] else "MISMATCH"
    print(f"{key:14}{silver[key]:>14}{gold[key]:>14}{mark:>10}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Where a mismatch comes from
# MAGIC
# MAGIC Almost always the dimension join. `bronze_accounts` holds one row per delivery, so an
# MAGIC account that appears in two exports appears twice, and joining usage to the raw table
# MAGIC multiplies every event for that account. The count below is greater than zero in the
# MAGIC normal case -- that is expected, and it is exactly why gold joins a deduplicated view.

repeated = session.sql(
    "SELECT account_id, count(*) AS deliveries FROM bronze_accounts "
    "GROUP BY account_id HAVING count(*) > 1 ORDER BY account_id"
).collect()
print(f"accounts delivered more than once: {len(repeated)}")
for row in repeated:
    print(f"  {row['account_id']}: {row['deliveries']} deliveries")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Daily shape
# MAGIC
# MAGIC More distinct dates than days of input is **correct**, not a bug: events near midnight
# MAGIC in offsets either side of UTC legitimately fall into the adjacent UTC day. A run over
# MAGIC two days of deliveries produces four dates with thin tails at each end.

for row in session.sql(
    "SELECT event_date, sum(events) AS events, sum(amount_cents) AS amount_cents "
    "FROM gold_daily_usage GROUP BY event_date ORDER BY event_date"
).collect():
    print(f"  {row['event_date']}  events {row['events']:>6}  cents {row['amount_cents']:>10}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## What was rejected
# MAGIC
# MAGIC Quarantined rows are kept and counted. A reason that suddenly dominates is a schema
# MAGIC change upstream.

for row in session.sql(
    "SELECT reason, count(*) AS n FROM quarantine GROUP BY reason ORDER BY n DESC, reason"
).collect():
    print(f"  {row['reason']:28} {row['n']}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Every gate

for check in quality.run_all(session.connection):
    print(check)

session.stop()
