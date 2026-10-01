# Databricks notebook source
# MAGIC %md
# MAGIC # Explore a landing-zone delivery
# MAGIC
# MAGIC Run this against a new drop **before** ingesting it. Everything here reads text and
# MAGIC counts; nothing writes to the warehouse, so it is safe on a delivery you do not trust
# MAGIC yet.
# MAGIC
# MAGIC Exported in the cell-delimited format the platform team's Databricks notebooks use.
# MAGIC It is also an ordinary Python file: `python notebooks/01_explore_raw.py` runs it top to
# MAGIC bottom. There is no cluster behind it -- see `src/etlduck/spark_compat.py`.

# COMMAND ----------

from etlduck.config import paths
from etlduck.profile import profile_landing_zone, render_profiles

LANDING = paths().raw
print(f"landing zone: {LANDING}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## What arrived
# MAGIC
# MAGIC Line counts, parse failures, and per-field presence. The number to look at first is
# MAGIC the parse-failure share: a delivery that was truncated in transit shows up here and
# MAGIC nowhere else until it has already been averaged into a rollup.

profiles = profile_landing_zone(LANDING)
print(render_profiles(profiles))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Compare against the last delivery
# MAGIC
# MAGIC A field that used to be universal and is now mostly absent is the signal that an
# MAGIC upstream producer changed its schema without telling anyone. Presence is compared
# MAGIC rather than row counts, because volume varies legitimately and presence does not.

if len(profiles) >= 2:
    previous, latest = profiles[-2], profiles[-1]
    fields = sorted(set(previous.fields) | set(latest.fields))
    print(f"{'field':20} {'previous':>10} {'latest':>10}")
    for name in fields:
        before = previous.fields.get(name)
        after = latest.fields.get(name)
        print(
            f"{name:20} "
            f"{(before.presence(previous.records) if before else 0.0):>9.1%} "
            f"{(after.presence(latest.records) if after else 0.0):>9.1%}"
        )
else:
    print("only one delivery present; nothing to compare against")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Findings
# MAGIC
# MAGIC These are observations, not failures. Profiling never rejects anything -- a row is
# MAGIC only ever rejected in silver, with a reason attached and a counter incremented.

for profile in profiles:
    for finding in profile.findings():
        print(f"- {finding}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Next
# MAGIC
# MAGIC If the delivery looks sane: `make run`, or `etlduck bronze && etlduck silver && etlduck
# MAGIC gold`. If it does not, say so in the channel before ingesting -- bronze keeps whatever
# MAGIC it is given, so a bad drop is recoverable but not free.
