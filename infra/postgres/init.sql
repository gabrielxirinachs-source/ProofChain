-- This runs automatically when the Postgres container starts for the first time.
-- pgvector must be enabled before SQLAlchemy can use vector columns.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";  -- For gen_random_uuid()

-- Confirm extensions loaded
SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector', 'uuid-ossp');