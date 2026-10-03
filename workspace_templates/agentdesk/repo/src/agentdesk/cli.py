"""Command line entry points.

``agentdesk bench`` is the only thing here that reports timings, and it reports them to a
human. Nothing asserts on them -- see ``tests/test_integration_latency.py`` for why the
guarantees are expressed as mechanisms instead.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from agentdesk import __version__, db
from agentdesk.assistant import digest, service as assistant
from agentdesk.assistant.recording import load_scripts, record
from agentdesk.assistant.tools import build_registry
from agentdesk.clock import now
from agentdesk.config import SETTINGS
from agentdesk.obs import MODEL_START, connections_held_across_model_calls, tracing
from agentdesk.serving import DESK_8B, Scheduler, plan_budget
from agentdesk.tickets import repository, service as desk
from agentdesk.tickets.models import Priority


def cmd_migrate(args: argparse.Namespace) -> int:
    """Apply pending migrations."""
    applied = db.migrate()
    print("\n".join(f"applied {name}" for name in applied) or "nothing to apply")
    return 0


def cmd_seed(args: argparse.Namespace) -> int:
    """Load the seeded tickets, skipping any already present."""
    path = SETTINGS.fixtures_dir / "tickets.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM tickets")
        existing = cur.fetchone()[0]
        if existing and not args.force:
            print(f"{existing} tickets already present; --force to reseed")
            return 0
        if args.force:
            cur.execute("TRUNCATE tickets RESTART IDENTITY CASCADE")
        for row in rows:
            cur.execute(
                "INSERT INTO tickets (subject, body, status, priority, requester, "
                "assignee, created_at, updated_at, summary, tags) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    row["subject"],
                    row["body"],
                    row["status"],
                    row["priority"],
                    row["requester"],
                    row["assignee"],
                    row["created_at"],
                    row["created_at"],
                    row["summary"],
                    row["tags"],
                ),
            )
        conn.commit()
    print(f"seeded {len(rows)} tickets")
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    """Draft a reply to one ticket and print the trace."""
    with tracing() as trace:
        result = asyncio.run(assistant.draft_reply(args.ticket_id, args.question))

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"question: {result['question']}\n")
        for step in result["steps"]:
            mark = "ok " if step["ok"] else "ERR"
            print(f"  [{mark}] {step['tool']}({json.dumps(step['arguments'])})")
            print(f"        {step['observation'].splitlines()[0][:100]}")
        print(f"\nanswer: {result['answer']}")
        print(f"citations: {', '.join(result['citations']) or 'none'}")
        held = connections_held_across_model_calls(trace)
        print(f"\nmodel calls: {trace.count(MODEL_START)}  held connections: {held or 'none'}")
    return 0


def cmd_dashboard(args: argparse.Namespace) -> int:
    """Print the queue digest."""
    with tracing() as trace:
        payload = digest.queue_digest(now=now(), rows=args.rows)

    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    banner = payload["banner"]
    print(
        f"{banner['total']} tickets | {banner['breached']} breached | "
        f"{banner['at_risk']} at risk | {banner['open']} open"
    )
    for row in payload["rows"]:
        flag = "BREACH" if row["breached"] else "risk  " if row["at_risk"] else "      "
        print(f"  {flag} #{row['id']:<4} {row['summary'][:70]}")
    print(f"\nmodel calls to render this page: {trace.count(MODEL_START)}")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    """Print the serving plan for the configured card."""
    budget = plan_budget(DESK_8B, vram_bytes=SETTINGS.vram_bytes)
    scheduler = Scheduler(DESK_8B, budget=budget)
    gib = 1024**3
    print(f"model          {DESK_8B}")
    print(f"card           {budget.total / gib:.1f} GiB")
    print(f"  weights      {budget.weights / gib:.2f} GiB")
    print(f"  reserved     {budget.reserved / gib:.3f} GiB")
    print(f"  kv cache     {budget.kv_available / gib:.2f} GiB")
    print(f"blocks         {scheduler.total_blocks} x {scheduler.block_bytes} bytes")
    print(f"cache tokens   {scheduler.total_blocks * 16}")
    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    """Time the dashboard and one draft.

    **Reported, never asserted.** A threshold here would be a coin flip on a shared
    runner. The numbers are for a human deciding whether something got worse.
    """
    start = time.perf_counter()
    digest.queue_digest(now=now())
    dashboard_ms = (time.perf_counter() - start) * 1000

    tickets = repository.list_tickets(limit=1)
    if not tickets:
        print("no tickets seeded; run `agentdesk seed` first")
        return 1

    start = time.perf_counter()
    asyncio.run(assistant.draft_reply(tickets[0].id, "What should I tell them?"))
    draft_ms = (time.perf_counter() - start) * 1000

    print(f"dashboard  {dashboard_ms:8.1f} ms")
    print(f"draft      {draft_ms:8.1f} ms")
    print("\nNot a gate. The guarantees are asserted as mechanisms, not timings --")
    print("see tests/test_integration_latency.py.")
    return 0


def _seed_matches_fixture() -> list[str]:
    """Return the ways the seeded tickets differ from fixtures/tickets.jsonl.

    **Recording against a stale database is the quietest way to break this repository.**

    Tool output is part of the cassette key, and the tools read tickets. If the fixture
    has been edited since the database was seeded -- and `agentdesk seed` skips when
    tickets are already present, so this is easy -- the recordings are keyed on data that
    no longer exists. Everything passes on the machine that recorded them and fails on
    the next fresh database, as a cassette miss in a test that names nothing useful.
    """
    rows = [
        json.loads(line)
        for line in (SETTINGS.fixtures_dir / "tickets.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    seeded = repository.list_tickets(limit=500)
    by_id = {ticket.id: ticket for ticket in seeded}

    problems: list[str] = []
    if len(seeded) != len(rows):
        problems.append(f"{len(seeded)} tickets seeded, {len(rows)} in the fixture")
    for index, row in enumerate(rows, start=1):
        ticket = by_id.get(index)
        if ticket is None:
            problems.append(f"#{index} is in the fixture and not in the database")
        elif ticket.body != row["body"] or ticket.subject != row["subject"]:
            problems.append(f"#{index} differs from the fixture")
    return problems


def cmd_cassettes(args: argparse.Namespace) -> int:
    """Regenerate the cassettes from the recording transcript."""
    problems = _seed_matches_fixture()
    if problems:
        print("refusing to record: the database does not match fixtures/tickets.jsonl")
        for problem in problems[:10]:
            print(f"  {problem}")
        print("\nRun `agentdesk seed --force` first. Recording against stale rows keys")
        print("every cassette on data that no longer exists, and the failure surfaces on")
        print("somebody else's fresh database as an unexplained miss.")
        return 1

    scripts = load_scripts(SETTINGS.fixtures_dir / "recordings.jsonl")
    registry = build_registry()
    directory = Path(SETTINGS.cassette_dir)

    if directory.exists():
        for stale in directory.glob("*.json"):
            stale.unlink()

    total = 0
    for script in scripts:
        keys = record(script, registry=registry, model=SETTINGS.model, cassette_dir=directory)
        total += len(keys)
        print(f"  {script.id}: {len(keys)} cassettes")
    print(f"{total} cassettes from {len(scripts)} scripts")
    return 0


def cmd_open(args: argparse.Namespace) -> int:
    """Open a ticket from the command line."""
    summary = asyncio.run(assistant.summarize_for_intake(args.subject, args.body))
    ticket = desk.open_ticket(
        subject=args.subject,
        body=args.body,
        requester=args.requester,
        priority=Priority(args.priority),
        summary=summary,
    )
    print(ticket)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser."""
    parser = argparse.ArgumentParser(prog="agentdesk", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("migrate", help="apply pending migrations").set_defaults(func=cmd_migrate)

    seed = sub.add_parser("seed", help="load the seeded tickets")
    seed.add_argument("--force", action="store_true", help="truncate and reseed")
    seed.set_defaults(func=cmd_seed)

    ask = sub.add_parser("ask", help="draft a reply to a ticket")
    ask.add_argument("ticket_id", type=int)
    ask.add_argument("question")
    ask.set_defaults(func=cmd_ask)

    dash = sub.add_parser("dashboard", help="print the queue digest")
    dash.add_argument("--rows", type=int, default=digest.DIGEST_ROWS)
    dash.set_defaults(func=cmd_dashboard)

    sub.add_parser("plan", help="print the serving plan").set_defaults(func=cmd_plan)
    sub.add_parser("bench", help="time the dashboard and one draft").set_defaults(func=cmd_bench)
    sub.add_parser("cassettes", help="regenerate cassettes").set_defaults(func=cmd_cassettes)

    new = sub.add_parser("open", help="open a ticket")
    new.add_argument("subject")
    new.add_argument("body")
    new.add_argument("--requester", default="someone@example.com")
    new.add_argument("--priority", default="normal", choices=[str(p) for p in Priority])
    new.set_defaults(func=cmd_open)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
