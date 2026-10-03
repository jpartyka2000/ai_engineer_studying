# agentdesk

A support ticket desk, with an assistant bolted on three years later.

That history is the whole shape of this repository. `tickets/` is the original product
and has to keep working when the assistant is down, slow or wrong. `assistant/` is the
thing that was added. `serving/` is the control plane for the model we self-host.

## Running it

```bash
cp .env.example .env     # the harness writes one for you; this is for running by hand
make up                  # build and start Postgres and the API
make migrate
make seed
make test                # this is what grading runs
```

Then:

```bash
make dashboard           # the queue, and how many model calls rendering it took
make ask ID=2 Q="What should I tell them about the VPN?"
make plan                # how the card divides up for the model we serve
make bench               # timings, for a human -- never a gate
make ci                  # everything CI runs
```

## Layout

```
src/agentdesk/
  tickets/      the desk: CRUD, search, SLA timers. Knows nothing about the assistant.
  assistant/    the agent: tool registry, prompt, loop, and where it meets a request
  serving/      VRAM arithmetic, the paged KV allocator, admission control
  llm/          conversation types and the recorded client
  obs/          probes that make a latency claim checkable by cause
```

## Three things that will save you an hour

**There is no live model and no GPU.** Every model response is replayed from
`fixtures/llm_cassettes/`, keyed on what the agent has observed so far -- read
`src/agentdesk/llm/recorded_client.py` before you change anything about the loop or the
tools. `serving/` is arithmetic; nothing in this repository runs inference.

**The clock is pinned** to `2025-06-18T09:00:00Z` via `AGENTDESK_NOW`. Tool output
carries SLA state, SLA state reaches the cassette key, so an unpinned clock would expire
every recording overnight. See `src/agentdesk/clock.py`.

**Latency is asserted as mechanism, never as milliseconds.** `make bench` prints real
numbers for you to look at, and nothing passes or fails on them. The rules that *are*
enforced are in `tests/test_integration_latency.py`: no pooled connection held across a
model call, no model call on the event loop thread, no model call per dashboard row.

## Where things are explained

The module docstrings carry the reasoning -- `recorded_client.py` for the cassette key,
`prompt.py` for the tool catalog and the fence, `loop.py` for the step budget,
`serving/memory.py` for where the bytes go, `obs/probes.py` for why there are no
stopwatches. `ARCHITECTURE.md` is the overview.
