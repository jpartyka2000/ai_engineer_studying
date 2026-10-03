-- The ticket store.
--
-- `summary` is nullable on purpose. It was added in 2024 when intake started writing a
-- cached one-line summary, and the tickets that predate it have none. Every reader must
-- cope with that -- see Ticket.display_summary -- because backfilling three years of
-- tickets through a model was not worth what it would have cost.

CREATE TABLE IF NOT EXISTS tickets (
    id          serial PRIMARY KEY,
    subject     text NOT NULL,
    body        text NOT NULL,
    status      text NOT NULL DEFAULT 'open',
    priority    text NOT NULL DEFAULT 'normal',
    requester   text NOT NULL,
    assignee    text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    summary     text,
    tags        text[] NOT NULL DEFAULT '{}',

    CONSTRAINT tickets_status_known
        CHECK (status IN ('open', 'pending', 'resolved', 'closed')),
    CONSTRAINT tickets_priority_known
        CHECK (priority IN ('urgent', 'high', 'normal', 'low'))
);

-- The queue page orders by this pair and nothing else, so one index serves it.
CREATE INDEX IF NOT EXISTS tickets_created_idx ON tickets (created_at DESC, id DESC);

-- requester_history filters on this.
CREATE INDEX IF NOT EXISTS tickets_requester_idx ON tickets (requester);
