# Architecture

## The shape, and why it is this shape

agentdesk was a support ticket desk for three years before anybody added AI to it. The
assistant arrived in 2024. Almost every rule in this repository exists because of that
order of events.

```
      tickets/  ──────────────┐         the original product
         ▲                    │         CRUD, search, SLA timers
         │                    ▼
   assistant/  ───────►  llm/           the agent, and the recorded model
         │
         ▼
       obs/                             probes: what a request spent

   serving/                             VRAM arithmetic. Depends on nothing.
```

Arrows are imports. The two that are missing matter more than the ones that are there:
`tickets/` imports neither `assistant/` nor `serving/`, and `tests/test_layering.py`
fails if that ever changes. One import is all it takes to turn a model outage into a
ticket-list outage.

## Decisions

### The model is recorded, and the key is not the prompt

`fixtures/llm_cassettes/` holds every response, keyed on

```
sha256(model | tools_digest | observations_digest | user_message | context_digest)
```

The two interesting parts are what is *in* and what is *out*.

**In: the observations.** The digest covers tool results as they appear in the message
list. That is what makes a loop recordable -- with nothing observed the model asks for a
tool, having seen its output it asks for the next, having seen both it answers. Progress
*is* the key moving. It also makes one bug self-announcing: a tool result appended under
the wrong role is not an observation, so the key does not move, so the model asks for the
same tool again and the loop circles.

**Out: the assembled prompt.** Keying on prompt bytes would mean any rewording turned
every request into a cassette miss, and nobody could improve an instruction without
re-recording the suite. Prompt *structure* is checked directly instead, in
`tests/test_prompt.py`.

The cost, stated plainly: this repository cannot tell you whether a better-worded prompt
produces a better answer, because the answer is fixed. It tells you whether the agent
asked for the right things, in the right order, and stopped when it should.

### Latency is a mechanism, not a measurement

There was a version of `tests/test_integration_latency.py` that asserted p95. It lasted
two weeks: it failed on busy runners, got a longer timeout, then another, and ended up
asserting nothing anybody believed. When it did fail it sent you to a profiler rather
than to a line.

Every guarantee is now structural and exact:

| rule | mechanism |
|---|---|
| the assistant must not drain the pool | no `db.connection()` span open when a model span starts |
| the assistant must not stall the process | model calls record a thread id, compared to the loop's |
| the dashboard must not scale with rows | count of model spans is zero, not "small" |

`agentdesk bench` still prints real timings. Nothing gates on them.

### Untrusted text is fenced, and the fence is not forgeable

Ticket bodies are written by the public and some of them contain instructions aimed at
the model. `prompt.fence()` wraps them in markers -- and neutralizes marker-shaped text
in the content first, because a fence that interpolates unchecked is theatre: the
attacker writes the closing marker themselves and everything after it reads as operator
instruction. Ticket 5 in the seed data carries exactly that payload, so the defence has a
live example rather than a hypothetical one.

### Admission reserves the peak; allocation is paged

Two questions, two mechanisms. *May this request start?* is answered by reserving enough
blocks for prompt plus every token it may generate. *Where does this token go?* is
answered by a paged allocator handing out blocks as the sequence grows.

Reserve the peak and allocate eagerly, and the card holds empty blocks for tokens nobody
will generate. Reserve nothing and allocate lazily, and the server admits a hundred
requests that each fit today and cannot all fit at token 300 -- a failure that lands
mid-generation and is invisible in a load test with short answers.

Preemption exists for when the reservations are nonetheless wrong. **A server preempting
under ordinary load is telling you its admission arithmetic is broken, not that it is
busy**, which is why `tests/test_serving_scheduler.py` asserts the preempted list is
empty rather than merely short.

### There is no GPU, and `serving/` says so

CI runs on CPU and exercises must be deterministic, so `torch` is not a dependency and
nothing here runs inference. `serving/` models the planning layer -- where the bytes go
and who may spend them -- in exact integer arithmetic. That is where production OOMs are
actually caused: the GPU did what it was told, it was told wrong.

What it does not give you is any familiarity with CUDA APIs. `serving/memory.py` is
explicit about the boundary.

### The clock is pinned

`AGENTDESK_NOW` fixes the clock in CI and in the container. SLA state reaches tool
output, tool output reaches the cassette key; an unpinned clock expires every recording
overnight. Production sets nothing and gets the real clock.

### The summary is written once

A ticket's one-line summary is generated at intake and stored in a column. Everything
downstream reads the column, and tickets older than the column fall back to truncating
the subject. The fallback is load-bearing: it is what makes it affordable for a list view
never to call a model.
