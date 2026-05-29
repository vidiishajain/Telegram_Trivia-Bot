# Deploying (Railway)

**Stage 8 — ship it.** We deploy with [Railway](https://docs.railway.com/) using its
**CLI** (no GitHub needed). Railway is the simplest reliable host for always-on apps and
bots: the Hobby plan (~$5/mo, includes some usage) **never sleeps**, so your Telegram bot
or web app stays up.

The project ships with a `Dockerfile`, so Railway builds the same container we run locally.

## One-time setup

```bash
brew install railway      # macOS. Other OSes: see https://docs.railway.com/
railway login             # opens your browser
```

## Deploy in 5 steps

```bash
# 1. Create a project (run this in your project folder)
railway init --name my-agent

# 2. Build + deploy the Dockerfile. If it says "multiple services / specify a service",
#    link the directory once with `railway service` (pick it), or add `--service my-agent`.
railway up

# 3. Set your secrets as Railway variables (NEVER commit .env — it's gitignored AND
#    dockerignored, so it's never in the image). Set every variable your app needs:
railway variables \
  --set "OPENROUTER_API_KEY=sk-or-..." \
  --set "APP_PASSWORD=pick-a-password" \
  --set "FAL_KEY=..." \
  --set "DATABASE_URL=postgresql://..."
  # ...and any R2_* you use

# 4. Give it a public URL
railway domain

# 5. Open it
railway open
```

## What gets deployed

The `Dockerfile` builds your project with `uv` and, by default, runs `src/agent/web.py`.
To deploy a **different entrypoint** (an example, a Telegram bot, a worker), add a
`railway.toml` at the repo root:

```toml
[deploy]
startCommand = "fastapi run path/to/app.py"   # a web app
# startCommand = "python -m agent.bot"          # a long-running bot/worker
```

(This repo's `railway.toml` is set to run the `examples/agent_idea_web` demo — change it to
your own app, or delete it to use the Dockerfile default.)

## Gotchas (learned the hard way — these are real)

- **Do NOT put `$PORT` in your start command.** Railway runs the start command *without a
  shell*, so `$PORT` is passed literally and the app fails with
  `'$PORT' is not a valid integer`. `fastapi run` already reads the `PORT` env var Railway
  injects and binds `0.0.0.0`, so just write `fastapi run app.py` — no `--port`, no `--host`.
- **Secrets are Railway variables, not your `.env`.** The `.env` file never reaches the
  image (gitignored + dockerignored). Set each value with `railway variables --set`.
- **Protect anything you expose publicly.**
  - A **web UI** → set `APP_PASSWORD` so it's behind a login (see `examples/agent_idea_web`,
    Pattern C). Otherwise it's open to the world and your API bill.
  - A **headless app with an HTTP endpoint** (e.g. a webhook receiver) → require a **secret
    token** on every request (a shared key in the URL or a header you check). Never deploy an
    open, unauthenticated endpoint.
  - A **bot with no inbound HTTP** (a polling Telegram bot) is already protected by its
    platform token — just keep that token secret.
- **Bots don't need a domain.** Only run `railway domain` for things that serve HTTP. A
  polling bot just needs to be running — skip the domain.
- **Database & migrations:** your app reaches out to Neon over the network; migrations run
  on startup (the demo calls `db.apply_migrations` in its lifespan). Nothing extra to do.

## Day-to-day

```bash
railway up                         # redeploy after code changes
railway variables --set "K=V"      # change a variable (triggers a redeploy)
railway logs                       # build/deploy/runtime logs (your first debugging stop)
railway status                     # project, environment, service, URL
railway open                       # open the dashboard
```

## Cost

Hobby plan is ~$5/mo and includes some usage; small apps/bots fit inside the included
credit. It never sleeps, which is the whole point for an always-on agent.
