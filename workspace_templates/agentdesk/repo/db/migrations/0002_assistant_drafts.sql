-- Drafts the assistant produced, kept so a human can review what it suggested and so
-- somebody can later ask how often the suggestion was used.
--
-- `steps` stores the COUNT of tool calls rather than the calls themselves. The full
-- trace is large, nobody has ever queried it, and a column that is written on every
-- request and read by nobody is a cost with no benefit. The trace stays in the logs.

CREATE TABLE IF NOT EXISTS assistant_drafts (
    id          serial PRIMARY KEY,
    ticket_id   integer NOT NULL REFERENCES tickets (id) ON DELETE CASCADE,
    question    text NOT NULL,
    answer      text NOT NULL,
    citations   text[] NOT NULL DEFAULT '{}',
    steps       integer NOT NULL DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS assistant_drafts_ticket_idx
    ON assistant_drafts (ticket_id, created_at DESC);
