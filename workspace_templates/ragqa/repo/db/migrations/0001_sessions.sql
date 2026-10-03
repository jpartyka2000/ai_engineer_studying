-- Conversation history.
--
-- The assistant is stateless about *answering* -- every question is retrieved and
-- answered on its own -- but the conversation is kept, for three reasons that have
-- nothing to do with generating replies: somebody needs to be able to see what the
-- assistant told an employee, the eval set is extended from real questions people
-- actually asked, and a refusal rate over time is the earliest signal that the corpus
-- has a gap.
--
-- Messages store the question, the answer, and the citations as given. Citations are a
-- text array rather than a join table on purpose: they are a snapshot of what was said
-- at the time, not a live reference. If a document is re-chunked next week the stored
-- citation should still record what the assistant claimed, even once the id no longer
-- resolves.

CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    user_email  TEXT NOT NULL,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES sessions(id),
    question    TEXT NOT NULL,
    answer      TEXT NOT NULL,
    refused     BOOLEAN NOT NULL,
    citations   TEXT[] NOT NULL DEFAULT '{}',
    asked_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- History is always read for one session, newest first.
CREATE INDEX IF NOT EXISTS messages_session_idx ON messages (session_id, asked_at DESC);
