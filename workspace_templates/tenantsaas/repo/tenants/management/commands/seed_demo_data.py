"""Seed realistic demo data.

Deterministic on purpose: a fixed seed means every scaffold of this exercise gets
byte-identical data, so an authored expectation stays true and a bug reproduces the
same way for everyone.
"""

import random
from datetime import datetime, timedelta, timezone

from django.core.management.base import BaseCommand
from django.db import transaction

from billing.models import LineItem
from projects.models import Project
from tenants.models import Tenant

RANDOM_SEED = 20260301

TENANTS = [
    ("Acme Corp", "acme", "key-acme-0001", Tenant.Plan.TEAM, 12, False),
    ("Globex", "globex", "key-globex-0002", Tenant.Plan.FREE, 3, False),
    ("Initech", "initech", "key-initech-0003", Tenant.Plan.ENTERPRISE, 140, False),
    ("Internal Support", "internal", "key-internal-0004", Tenant.Plan.ENTERPRISE, 8, True),
]

PROJECTS = {
    "acme": ["Website", "Mobile App", "Data Warehouse"],
    "globex": ["Prototype"],
    "initech": ["Core Platform", "Reporting", "Integrations", "Archive"],
    "internal": ["Support Tooling"],
}


class Command(BaseCommand):
    """Create demo tenants, projects and three months of billable usage."""

    help = "Seed deterministic demo tenants, projects and line items."

    def add_arguments(self, parser) -> None:
        """Register command arguments."""
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing demo data before seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        """Seed the database."""
        rng = random.Random(RANDOM_SEED)

        if options["reset"]:
            LineItem.objects.all().delete()
            Project.objects.all().delete()
            Tenant.objects.all().delete()
            self.stdout.write("Cleared existing demo data.")

        tenants: dict[str, Tenant] = {}
        for name, slug, api_key, plan, seats, internal in TENANTS:
            tenant, _ = Tenant.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "api_key": api_key,
                    "plan": plan,
                    "seat_count": seats,
                    "is_internal": internal,
                },
            )
            tenants[slug] = tenant

        projects: dict[str, list[Project]] = {}
        for slug, names in PROJECTS.items():
            created = []
            for project_name in names:
                project, _ = Project.objects.update_or_create(
                    tenant=tenants[slug],
                    slug=project_name.lower().replace(" ", "-"),
                    defaults={"name": project_name, "storage_bytes": rng.randint(10**7, 10**10)},
                )
                created.append(project)
            projects[slug] = created

        # Three full months, so an invoice can be built for any of them and the
        # month-boundary behaviour is exercised by real data.
        kinds = [LineItem.Kind.SEAT, LineItem.Kind.STORAGE, LineItem.Kind.API_CALL]
        item_count = 0
        for slug, tenant in tenants.items():
            for month in (1, 2, 3):
                # Include the last day of each month explicitly: that is where the
                # inclusive-period contract is easiest to get wrong.
                last_day = (datetime(2026, month + 1, 1, tzinfo=timezone.utc) - timedelta(days=1)).day
                days = sorted({1, 7, 14, 21, last_day})
                for day in days:
                    for project in projects[slug]:
                        LineItem.objects.create(
                            tenant=tenant,
                            project=project,
                            kind=rng.choice(kinds),
                            description=f"{project.name} usage {2026}-{month:02d}-{day:02d}",
                            amount_cents=rng.randrange(100, 9_000, 50),
                            created_at=datetime(
                                2026, month, day, rng.randrange(0, 24), 30, tzinfo=timezone.utc
                            ),
                        )
                        item_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(tenants)} tenants, "
                f"{sum(len(v) for v in projects.values())} projects, "
                f"{item_count} line items."
            )
        )
