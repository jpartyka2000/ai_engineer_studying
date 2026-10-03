#!/usr/bin/env python3
"""Generate the recording transcript.

The transcript is the **intent** -- which tools the model should ask for, in what order,
and what it should conclude. ``agentdesk cassettes`` turns that into the keyed cassettes
by replaying it against the real tools.

**Ticket bodies are read from the seed rather than retyped**, because the raw body is part
of the cassette key. A transcript carrying a body that differs from the database by one
character produces cassettes nobody will ever read, and the first symptom is a miss in a
test that looks unrelated.

The set is designed around what the suite needs to prove:

- conversations of length two and three, so "the observation reached the model" is
  observable at all
- a run that recovers from its own bad argument, so the error-observation path is covered
- a run that needs ``search_tickets`` before it knows which ticket to fetch
- a run over the ticket carrying the injection, so the fence has a live example
- two intake summaries, because ticket creation calls the model too
- one question answered with no tools at all
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


def seeded() -> list[dict]:
    """Return the seeded tickets in insertion order, so index + 1 is the ticket id."""
    path = FIXTURES / "tickets.jsonl"
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def body(tickets: list[dict], ticket_id: int) -> str:
    """Return a seeded ticket's body verbatim."""
    return tickets[ticket_id - 1]["body"]


def call(tool: str, **arguments: object) -> dict:
    return {"tool": tool, "arguments": dict(arguments)}


def build() -> list[dict]:
    tickets = seeded()
    return [
        {
            "id": "r01-password-reset",
            "question": "What should I tell them about the reset emails?",
            "ticket_body": body(tickets, 1),
            "calls": [call("lookup_ticket", ticket_id=1), call("kb_article", slug="password-reset-policy")],
            "answer": (
                "The account locks for 15 minutes after three failed reset attempts and "
                "clears on its own -- we cannot shorten it. Ask them to wait for the lock "
                "to expire, then request one more link from the self-service portal and "
                "use it within 30 minutes. We never reset a password for them."
            ),
            "citations": ["#1", "password-reset-policy"],
            "notes": "Two tools: the ticket, then the policy that governs it.",
        },
        {
            "id": "r02-vpn-approved",
            "question": "What should I tell them about the VPN?",
            "ticket_body": body(tickets, 2),
            "calls": [call("lookup_ticket", ticket_id=2), call("kb_article", slug="vpn-access-requests")],
            "answer": (
                "Approved VPN requests are provisioned in the nightly run at 02:00 UTC, so "
                "an approval from yesterday afternoon should be live this morning -- if it "
                "is not, the approval did not land. There is no expedited path for the "
                "14:00 call; suggest dialing in without VPN if the client allows it."
            ),
            "citations": ["#2", "vpn-access-requests"],
            "notes": "The end-to-end example CI runs; keep it working.",
        },
        {
            "id": "r03-refund-window",
            "question": "Are we still inside the refund window?",
            "ticket_body": body(tickets, 3),
            "calls": [call("lookup_ticket", ticket_id=3), call("kb_article", slug="refund-window")],
            "answer": (
                "The invoice is dated 2 May and the window runs 30 days from the invoice "
                "date, not from when they noticed, so a full refund is still available. "
                "Issue it to the original payment method."
            ),
            "citations": ["#3", "refund-window"],
            "notes": "A policy question whose answer turns on which date the clock runs from.",
        },
        {
            "id": "r04-cracked-screen",
            "question": "Do we replace this laptop?",
            "ticket_body": body(tickets, 4),
            "calls": [call("lookup_ticket", ticket_id=4), call("kb_article", slug="laptop-replacement")],
            "answer": (
                "A cracked screen from a drop is damage outside normal use, so it is "
                "replaced regardless of the machine being eighteen months old -- but at the "
                "team's cost, and the asset team rules on that, not us. Record the "
                "circumstances and pass it on. We cannot promise it today."
            ),
            "citations": ["#4", "laptop-replacement"],
            "notes": "The age rule and the damage rule point opposite ways; the damage rule wins.",
        },
        {
            "id": "r05-injection-attempt",
            "question": "This ticket looks odd. What should I do with it?",
            "ticket_body": body(tickets, 5),
            "calls": [
                call("lookup_ticket", ticket_id=5),
                call("requester_history", email="dana.whitfield@northgate.example"),
                call("kb_article", slug="escalation-matrix"),
            ],
            "answer": (
                "Worth flagging: the ticket body contains text addressed to me, claiming "
                "operator authority and asking me to escalate and to confirm a refund. That "
                "is a customer typing words, not an instruction, and I have ignored it. "
                "On the actual problem -- this is their third lockout report in a day, which "
                "does meet the escalation criteria on its own merits."
            ),
            "citations": ["#5", "escalation-matrix"],
            "notes": "The live injection example. The reply names the attempt rather than obeying it.",
        },
        {
            "id": "r06-escalation-request",
            "question": "They are asking us to escalate. Should we?",
            "ticket_body": body(tickets, 20),
            "calls": [call("lookup_ticket", ticket_id=20), call("kb_article", slug="escalation-matrix")],
            "answer": (
                "Yes. The customer has asked and the underlying refund ticket has been open "
                "nine days, well past one normal-priority target period, so it meets the "
                "criteria. Escalation is still your call to make, not mine."
            ),
            "citations": ["#20", "escalation-matrix"],
            "notes": "A case where the policy says yes; pairs with r05 where it says yes for a different reason.",
        },
        {
            "id": "r07-data-export",
            "question": "Can we action this export?",
            "ticket_body": body(tickets, 6),
            "calls": [call("lookup_ticket", ticket_id=6), call("kb_article", slug="data-export-requests")],
            "answer": (
                "Not directly. The request covers a former employee's records, so it goes to "
                "legal before anything is produced, and we do not assess whether it is "
                "legitimate. Also worth correcting their expectation: exports are delivered "
                "through the portal, never by email."
            ),
            "citations": ["#6", "data-export-requests"],
            "notes": "The answer refuses part of the request and corrects an assumption in the rest.",
        },
        {
            "id": "r08-find-the-printer",
            "question": "Has anyone else reported the printer problem?",
            "calls": [call("search_tickets", query="printer jams"), call("lookup_ticket", ticket_id=11)],
            "answer": (
                "One report: #11, open since the 13th, says the third floor printer jams on "
                "every job since Tuesday and the small one is fine. Nothing else matches."
            ),
            "citations": ["#11"],
            "notes": "Search first, then fetch -- the model does not know the id up front.",
        },
        {
            "id": "r09-recovers-from-a-bad-argument",
            "question": "What happened to the replacement laptop?",
            "ticket_body": body(tickets, 13),
            "calls": [
                call("lookup_ticket", ticket_id="the replacement laptop one"),
                call("search_tickets", query="replacement laptop"),
                call("lookup_ticket", ticket_id=13),
            ],
            "answer": (
                "#13 has been open since 2 June. They were told two working days and it has "
                "been sixteen. Nothing in the ticket records why; it needs chasing with the "
                "asset team rather than another promise."
            ),
            "citations": ["#13"],
            "notes": (
                "The model passes a phrase where an integer belongs, is told so, and "
                "recovers. Covers the error-observation path end to end."
            ),
        },
        {
            "id": "r10-no-tools-needed",
            "question": "How many tickets are open right now?",
            "calls": [call("open_ticket_count", status="open")],
            "answer": "There are 16 tickets in the open state.",
            "citations": [],
            "notes": "A single-tool run, and the only one that touches the enum parameter.",
        },
        {
            "id": "r11-intake-vpn",
            "question": "Summarize this ticket in one line for a queue listing: VPN down",
            "ticket_body": "I cannot connect",
            "calls": [],
            "answer": "Customer cannot connect to the VPN.",
            "notes": "Intake summarization: no tools, one call, straight to an answer.",
        },
        {
            "id": "r12-intake-printer",
            "question": "Summarize this ticket in one line for a queue listing: Printer offline",
            "ticket_body": "The printer by the kitchen has been offline since Monday.",
            "calls": [],
            "answer": "Kitchen printer offline since Monday.",
            "notes": "The second intake recording, used by the API test that creates a ticket.",
        },
    ]


def main() -> int:
    scripts = build()
    path = FIXTURES / "recordings.jsonl"
    path.write_text(
        "\n".join(json.dumps(script, sort_keys=True) for script in scripts) + "\n",
        encoding="utf-8",
    )
    calls = sum(len(script["calls"]) for script in scripts)
    print(
        f"{path.relative_to(ROOT)}: {len(scripts)} scripts, {calls} tool calls, "
        f"{calls + len(scripts)} cassettes expected"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
