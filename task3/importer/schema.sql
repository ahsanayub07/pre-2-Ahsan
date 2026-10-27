-- Table for the Task 3 articles. Safe to run many times (IF NOT EXISTS).
CREATE TABLE IF NOT EXISTS articles (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    url             TEXT         NOT NULL UNIQUE,   -- reliable identifier, used for duplicates
    source          VARCHAR(100) NOT NULL,
    title           TEXT         NOT NULL,
    author          TEXT,
    published_date  DATE,
    published_time  TIMETZ,                         -- times without an offset are stored as UTC
    description     TEXT,
    tags            TEXT[]       NOT NULL DEFAULT '{}',
    language        VARCHAR(10),
    body            TEXT         NOT NULL,
    word_count      INTEGER      NOT NULL CHECK (word_count >= 0),
    method          VARCHAR(20),
    imported_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_articles_source         ON articles (source);
CREATE INDEX IF NOT EXISTS idx_articles_published_date ON articles (published_date);
