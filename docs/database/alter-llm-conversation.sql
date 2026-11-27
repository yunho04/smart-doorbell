-- PostgreSQL schema change for the LLM result and conversation.
BEGIN;

ALTER TABLE events
    ADD COLUMN purpose TEXT,
    ADD COLUMN conversation_summary TEXT;

ALTER TABLE event_responses
    ADD COLUMN turn_no INTEGER,
    ADD COLUMN visitor_text TEXT,
    ADD COLUMN purpose TEXT;

COMMIT;
