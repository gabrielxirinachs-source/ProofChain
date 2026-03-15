# Deployment Guide

ProofChain deploys to [Fly.io](https://fly.io) via GitHub Actions.

---

## First-Time Setup

### 1. Install Fly CLI
```bash
curl -L https://fly.io/install.sh | sh
```

### 2. Login and create the app
```bash
fly auth login
fly launch --name proofchain-api --region mia --no-deploy
```

### 3. Set production secrets
```bash
# Required
fly secrets set OPENAI_API_KEY=sk-your-key-here

# Optional: add a managed Postgres + Redis
fly postgres create --name proofchain-db
fly redis create --name proofchain-redis
```

### 4. Add FLY_API_TOKEN to GitHub
```bash
# Get your token
fly auth token

# Add it to GitHub:
# Repository → Settings → Secrets and variables → Actions
# New secret: FLY_API_TOKEN = <token from above>
```

### 5. Deploy
```bash
fly deploy
```

Or just push to `main` — GitHub Actions deploys automatically.

---

## Useful Commands

```bash
# View live logs
fly logs

# Open a shell in the running container
fly ssh console

# Check app status
fly status

# Scale up (if you need more memory)
fly scale memory 1024

# View metrics
fly dashboard
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key |
| `DATABASE_URL` | Yes | Postgres connection string |
| `REDIS_URL` | Yes | Redis connection string |
| `ENV` | No | `production` (set automatically) |

---

## Architecture in Production

```
Internet → Fly.io Edge → ProofChain API (Docker)
                              │
                    ┌─────────┼─────────┐
                    ▼         ▼         ▼
                Postgres    Redis    OpenAI API
               (pgvector)  (cache)  (LLM calls)
```