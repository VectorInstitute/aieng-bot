# aieng-bot Slack Agent

Slack agent for the Vector Institute workspace, built on Slack Bolt +
Socket Mode. Phase 1 is a dummy agent that proves out the plumbing —
install, per-thread context isolation, background listening, and
auto-deploy — before the real agent layer (Claude Agent SDK, Managed
Agents, or a custom harness) is wired into `respond_to()` in `app.py`.

## Architecture

```
Slack event (mention, DM, channel message, slash command)
  → Socket Mode (outbound WebSocket — no public URL, no inbound firewall rules)
  → Bolt handler records the message into a per-(channel, thread) ContextStore
  → respond_to() produces a reply   ← replace with the real agent layer
  → reply posted back to the same thread
```

Every Slack thread and DM gets an isolated context keyed by
`(channel, thread_ts)` — the same model Claude Tag uses. The bot
listens to all messages in channels it is invited to (recording them
for context) but only speaks when @mentioned or DMed.

## One-time setup

### 1. Create the Slack app

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From an app manifest**
2. Pick the Vector workspace, paste the contents of `manifest.yaml` (YAML tab), and create the app

### 2. Generate tokens

1. **App-level token**: Basic Information → App-Level Tokens → Generate — add scope `connections:write`. Copy the `xapp-…` token.
2. **Bot token**: OAuth & Permissions → **Install to Workspace** (or **Request to Install** if the workspace requires admin approval — see below). Copy the `xoxb-…` token after install.

> **Admin approval note**: the `channels:history` / `groups:history`
> scopes let the bot read messages in channels it is *explicitly
> invited to* (needed for background context). Socket Mode means no
> inbound network access — only an outbound WebSocket to
> `wss-primary.slack.com`. Message text is processed by the bot
> service; nothing is sent to an LLM yet in phase 1.

### 3. Run locally

```bash
cd slack_agent
cp .env.example .env   # fill in both tokens
uv sync
uv run python app.py
```

## Test plan (dummy channel)

1. Create a test channel (e.g. `#aieng-bot-test`) and `/invite @aieng-bot`
2. `@aieng-bot hello` — replies in-thread with version, build SHA, and its context for that thread
3. Post a few plain messages (no mention), then mention it again in the same thread — the tracked message count grows: **background listening works**
4. Mention it in a *different* thread — count starts fresh: **contexts are isolated**
5. DM the bot — it replies without needing a mention
6. `/aieng-bot version` — shows the running build SHA (verifies a deploy picked up your latest changes)

## Continuous deployment

`.github/workflows/deploy-slack-agent.yml` builds and deploys to Cloud
Run (project `coderd`, Toronto) on every push to `main` touching
`slack_agent/**`. Because Socket Mode connects outbound, redeploying
the service is all it takes for changes to reflect in Slack — the
Slack app config itself only changes when you edit scopes/events, which
requires updating the manifest at api.slack.com (and re-installing if
scopes changed).

Required GitHub secrets (repo → Settings → Secrets):

- `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN` — from step 2 above
- `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT` — already set up for the bookstack/dashboard deploys

The service runs exactly one always-on instance (`--min-instances=1
--max-instances=1 --no-cpu-throttling`) because Socket Mode holds a
persistent WebSocket and the context store is in-memory. The HTTP port
only serves `/health`.

## Roadmap

- [ ] Phase 1: dummy bot installed in the Vector workspace (this)
- [ ] Persist thread contexts (currently in-memory, lost on redeploy)
- [ ] Wire the agent layer into `respond_to()` (Claude Agent SDK / Managed Agents / custom harness)
- [ ] Tools & APIs one by one (GitHub, dashboards, BookStack, …)
- [ ] Optional: Slack "Agents & AI Apps" assistant surface (`assistant:write`, split-view pane) — needs a scope addition + re-install
