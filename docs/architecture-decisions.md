# Architecture Decision Records (ADR)

ADRs document *why* we made technical choices — not just what we chose.
This is valuable for job interviews and team onboarding.

---

## ADR-001: PostgreSQL + pgvector over a dedicated vector DB

**Date:** Phase 1
**Status:** Accepted

**Context:**
We need to store evidence nodes with both structured data (relationships, timestamps, provenance) and semantic embeddings (for similarity search over evidence).

**Decision:**
Use PostgreSQL with the pgvector extension rather than a separate vector database like Pinecone or Weaviate.

**Reasons:**
- One fewer service to operate and pay for
- Evidence nodes have rich relational structure (claim → edge → source) that SQL handles well
- pgvector is production-proven (used at scale by Supabase, etc.)
- Qdrant remains an option (listed in .env) if we hit pgvector performance limits

**Trade-offs:**
- pgvector is slower than dedicated vector DBs at very large scale (10M+ vectors)
- Acceptable for this project; can migrate later if needed

---

## ADR-002: LangGraph over raw LangChain for the agent loop

**Date:** Phase 1 (implementation: Phase 5)
**Status:** Accepted

**Context:**
The agent must follow an MDP-like loop: query KG → expand nodes → web search → rank → decide to continue or stop.

**Decision:**
Use LangGraph's `StateGraph` to model the agent as an explicit state machine.

**Reasons:**
- Explicit nodes + edges = inspectable, debuggable control flow
- State is typed (Pydantic), making the evidence graph a first-class object
- Supports cycles (the MDP loop) natively
- LangChain AgentExecutor is a black box by comparison

---

## ADR-003: Redis for caching, not persistent storage

**Date:** Phase 1
**Status:** Accepted

**Context:**
Repeated `/verify` calls for the same claim should be fast (sub-second).

**Decision:**
Cache serialized verification results in Redis with a TTL of 1 hour.

**Reasons:**
- Fact-checking results for a given claim don't change minute-to-minute
- Redis is in-memory = microsecond reads
- TTL ensures stale verdicts don't persist forever

**Trade-offs:**
- Cache invalidation needed if evidence is manually updated (Phase 6 concern)