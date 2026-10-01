#!/usr/bin/env python
"""Generate landing-zone files.

The files committed under ``raw/`` were produced by this script with its default arguments,
which is why the suite can assert exact counts: the generator is seeded, so it emits the
same bytes every time on every platform.

    python tools/gen_seed_data.py --out raw            # regenerate the committed files
    python tools/gen_seed_data.py --out /tmp/big --events-per-day 20000

The second form is what the benchmark uses. Volume lives in a scratch directory rather than
in git, because a megabyte of synthetic JSON in a repository is a megabyte everybody clones
forever and nobody reads.

**The defects are deliberate and fixed.** Each generated day contains one unparseable line,
one naive timestamp, one unknown event type, one decimal amount and one event with no
account -- the cases silver has to quarantine with a reason. One event in the second day is
a replay of one from the first, because the upstream delivers at least once. And a handful
of events sit within a few hours of midnight in offsets either side of UTC, so a date
derived in the wrong zone lands on the wrong day. A generator that only produced clean rows
would let every one of those bugs through the suite.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

#: Offsets the upstream sends. Mixed on purpose: every one of these is a real customer
#: timezone and the pipeline must land them all on the same UTC timeline.
OFFSETS = ("+00:00", "-05:00", "+05:30", "+09:00", "-08:00", "Z")

EVENT_TYPES = ("api_call", "export", "seat_active", "storage_gb")
PLANS = ("free", "team", "enterprise")
COUNTRIES = ("DE", "US", "IN", "JP", "BR", "GB")

#: Names include non-ASCII deliberately: an export that mangles encoding is a real failure
#: and the loader claims to read UTF-8 with a BOM tolerated.
NAME_STEMS = ("Müller", "O'Brien", "Nakamura", "Åberg", "Díaz", "Zhang", "Kowalski", "Okonjo")

DEFAULT_START = date(2026, 3, 1)


def _accounts(count: int) -> list[dict[str, str]]:
    """Build the account dimension deterministically."""
    return [
        {
            "account_id": f"acct-{index:03d}",
            "name": f"{NAME_STEMS[index % len(NAME_STEMS)]} GmbH {index}",
            "plan": PLANS[index % len(PLANS)],
            "country": COUNTRIES[index % len(COUNTRIES)],
        }
        for index in range(count)
    ]


def write_accounts(out: Path, accounts: list[dict[str, str]]) -> Path:
    """Write the full account dimension as CSV."""
    path = out / "accounts.csv"
    lines = ["account_id,name,plan,country"]
    lines += [f"{a['account_id']},{a['name']},{a['plan']},{a['country']}" for a in accounts]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_accounts_delta(out: Path, accounts: list[dict[str, str]]) -> Path:
    """Write a later, partial delivery that upgrades two accounts' plans.

    This is why the dimension has to be collapsed before it is joined: after both files are
    loaded, two accounts have two rows in ``bronze_accounts``.
    """
    path = out / "accounts_delta.csv"
    upgraded = accounts[:2]
    lines = ["account_id,name,plan,country"]
    lines += [f"{a['account_id']},{a['name']},enterprise,{a['country']}" for a in upgraded]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _event(
    rng: random.Random, accounts: list[dict[str, str]], day: date, index: int
) -> dict[str, str]:
    """Build one well-formed event."""
    account = accounts[rng.randrange(len(accounts))]
    event_type = EVENT_TYPES[rng.randrange(len(EVENT_TYPES))]
    offset = OFFSETS[index % len(OFFSETS)]

    # Most events sit in the middle of the day; every seventh is pushed to within a couple
    # of hours of midnight, which is where a date computed in the wrong zone goes wrong.
    if index % 7 == 0:
        hour, minute = 22 + (index % 2), rng.randrange(0, 60)
    else:
        hour, minute = rng.randrange(6, 20), rng.randrange(0, 60)

    stamp = f"{day.isoformat()}T{hour:02d}:{minute:02d}:{rng.randrange(0, 60):02d}"
    occurred_at = f"{stamp}Z" if offset == "Z" else f"{stamp}{offset}"

    return {
        "event_id": f"evt-{day.isoformat()}-{index:05d}",
        "account_id": account["account_id"],
        "event_type": event_type,
        "occurred_at": occurred_at,
        "quantity": str(rng.randrange(1, 40)),
        "amount_cents": str(rng.randrange(5, 4000)),
    }


def write_usage_day(
    out: Path,
    rng: random.Random,
    accounts: list[dict[str, str]],
    day: date,
    events_per_day: int,
    replay: dict[str, str] | None,
) -> tuple[Path, dict[str, str]]:
    """Write one day of usage events, with the fixed set of deliberate defects.

    Args:
        out: Output directory.
        rng: Seeded generator.
        accounts: The dimension.
        day: The day to generate.
        events_per_day: How many well-formed events to emit.
        replay: An event from a previous day to re-deliver, or None.

    Returns:
        ``(path, first_event)`` -- the first event is handed back so the caller can replay it
        on a later day.
    """
    path = out / f"usage_events_{day.isoformat()}.jsonl"
    events = [_event(rng, accounts, day, index) for index in range(events_per_day)]
    first = dict(events[0])

    lines = [json.dumps(event, ensure_ascii=False) for event in events]

    # The deliberate defects, at fixed positions so counts are stable.
    naive = dict(events[events_per_day // 5])
    naive["event_id"] += "-naive"
    naive["occurred_at"] = f"{day.isoformat()} 11:30:00"
    lines.append(json.dumps(naive))

    unknown = dict(events[events_per_day // 4])
    unknown["event_id"] += "-unknown"
    unknown["event_type"] = "beta_feature_probe"
    lines.append(json.dumps(unknown))

    decimal = dict(events[events_per_day // 3])
    decimal["event_id"] += "-decimal"
    decimal["amount_cents"] = "12.50"
    lines.append(json.dumps(decimal))

    orphan = dict(events[events_per_day // 2])
    orphan["event_id"] += "-noacct"
    orphan["account_id"] = ""
    lines.append(json.dumps(orphan))

    lines.append('{"event_id": "evt-truncated", "account_id": "acct-000", "event_ty')

    if replay is not None:
        lines.append(json.dumps(replay, ensure_ascii=False))

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path, first


def generate(
    out: Path,
    accounts_count: int = 8,
    days: int = 2,
    events_per_day: int = 200,
    seed: int = 20260301,
    start: date = DEFAULT_START,
) -> list[Path]:
    """Generate the whole landing zone.

    Returns:
        Every path written, in the order written.
    """
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    accounts = _accounts(accounts_count)

    written = [write_accounts(out, accounts), write_accounts_delta(out, accounts)]
    replay: dict[str, str] | None = None
    for offset_days in range(days):
        day = start + timedelta(days=offset_days)
        path, first = write_usage_day(out, rng, accounts, day, events_per_day, replay)
        written.append(path)
        # Replay the first event of day one on day two, the way an at-least-once producer
        # does after a failed acknowledgement.
        replay = first if offset_days == 0 else replay
    return written


def main(argv: list[str] | None = None) -> int:
    """Generate the files and report what was written."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("raw"))
    parser.add_argument("--accounts", type=int, default=8)
    parser.add_argument("--days", type=int, default=2)
    parser.add_argument("--events-per-day", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20260301)
    args = parser.parse_args(argv)

    written = generate(
        args.out,
        accounts_count=args.accounts,
        days=args.days,
        events_per_day=args.events_per_day,
        seed=args.seed,
    )
    for path in written:
        print(f"wrote {path} ({path.stat().st_size} bytes)")
    print(f"generated at {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
