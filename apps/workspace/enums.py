"""Shared vocabularies for workspace mode.

Defined once here and imported by both ``models.py`` and ``schemas.py`` so the
Django choices and the Pydantic validation can never drift apart. Django's
``TextChoices`` subclasses ``str`` and ``Enum``, so Pydantic v2 accepts these
directly as field annotations.

This is a deliberate correction of a bug pattern in ``apps/coding``, where
``challenge_type``, ``language`` and ``difficulty`` are plain ``str`` on the
Pydantic side with no enum validation -- letting a bad LLM value reach the
database column unchecked.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class ExerciseType(models.TextChoices):
    """The ten kinds of work an exercise can ask for."""

    CRITICAL_BUG = "critical_bug", _("Fix a critical bug fast")
    LATENCY = "latency", _("Fix a severe latency issue")
    ML_DEPLOY = "ml_deploy", _("Implement and deploy an ML model")
    ETL_PIPELINE = "etl_pipeline", _("Build or fix a data/ETL pipeline")
    GENAI_CHATBOT = "genai_chatbot", _("Fix a generative-AI QA chatbot")
    EDA_LIBRARY = "eda_library", _("Build or fix an EDA/preprocessing library")
    TENANT_ISOLATION = "tenant_isolation", _("Ensure tenant isolation for text-to-SQL")
    EVAL_FRAMEWORK = "eval_framework", _("Create or fix a genAI evaluation framework")
    ANALYTICS_FEATURES = "analytics_features", _("Add analytics/statistical features")
    CICD_PIPELINE = "cicd_pipeline", _("Fix a broken or flaky CI/CD pipeline")


class Difficulty(models.TextChoices):
    """Difficulty tiers, matching the vocabulary used elsewhere in the project."""

    BEGINNER = "beginner", _("Beginner")
    INTERMEDIATE = "intermediate", _("Intermediate")
    ADVANCED = "advanced", _("Advanced")


class BaseApp(models.TextChoices):
    """The seven reusable base applications exercises are built on.

    Exercises are ``(base_app, mutations)`` pairs rather than 50 unrelated
    codebases; this is what makes the catalog authorable.
    """

    TENANTSAAS = "tenantsaas", _("Django multi-tenant SaaS (Postgres)")
    PREDICTSVC = "predictsvc", _("FastAPI ML prediction service")
    ETLDUCK = "etlduck", _("DuckDB warehouse / ETL pipeline")
    RAGQA = "ragqa", _("RAG / generative-AI QA chatbot")
    SQLGENIE = "sqlgenie", _("Text-to-SQL chatbot (multi-tenant Postgres)")
    EVENTSTORE = "eventstore", _("MongoDB event store + performance model")
    EDAKIT = "edakit", _("EDA / data-preprocessing library")


class Database(models.TextChoices):
    """Databases an exercise can require.

    Amazon RDS is emulated as Postgres plus realistic RDS artifacts in config
    (parameter groups, IAM-auth settings, replica endpoints) rather than being a
    distinct backend, because RDS is a managed service that cannot run locally.
    """

    POSTGRES = "postgres", _("PostgreSQL")
    MONGODB = "mongodb", _("MongoDB")
    DUCKDB = "duckdb", _("DuckDB (serverless)")


class CheckKind(models.TextChoices):
    """Kinds of objective acceptance check the harness can run."""

    PYTEST = "pytest", _("Specific pytest node")
    PYTEST_SUITE = "pytest_suite", _("Whole suite vs baseline")
    FILE_UNCHANGED = "file_unchanged", _("Protected file hashes match")
    BENCHMARK = "benchmark", _("Benchmark script metric threshold")
    METRIC = "metric", _("Model/eval metric threshold")
    CMD = "cmd", _("Command exit code")
    GREP_ABSENT = "grep_absent", _("Pattern must not appear")
    GREP_PRESENT = "grep_present", _("Pattern must appear")
    FLAKE_REPEAT = "flake_repeat", _("Test passes N/N under CI env")
    LLM = "llm", _("Delegated to model judgment")


class CheckStatus(models.TextChoices):
    """Outcome of running a single check."""

    PASSED = "passed", _("Passed")
    FAILED = "failed", _("Failed")
    ERROR = "error", _("Could not run")
    TIMEOUT = "timeout", _("Timed out")
    SKIPPED = "skipped", _("Skipped")


class ObjectiveStatus(models.TextChoices):
    """Whether the objective half of the grade could be determined at all.

    ``INDETERMINATE`` exists so a broken laptop -- Docker down, a port conflict,
    a harness timeout -- never scores zero. The grade falls back to model
    judgment and is labelled provisional.
    """

    COMPLETE = "complete", _("All checks ran")
    PARTIAL = "partial", _("Some checks could not run")
    INDETERMINATE = "indeterminate", _("Checks could not be run")


class LetterGrade(models.TextChoices):
    """The 13-point letter scale, best first.

    Values are kept in sync with ``apps.workspace.grading.LETTER_CUTOFFS`` by a
    unit test; ``grading`` stays free of Django so it can be tested without
    settings.
    """

    A_PLUS = "A+", _("A+")
    A = "A", _("A")
    A_MINUS = "A-", _("A-")
    B_PLUS = "B+", _("B+")
    B = "B", _("B")
    B_MINUS = "B-", _("B-")
    C_PLUS = "C+", _("C+")
    C = "C", _("C")
    C_MINUS = "C-", _("C-")
    D_PLUS = "D+", _("D+")
    D = "D", _("D")
    D_MINUS = "D-", _("D-")
    F = "F", _("F")
