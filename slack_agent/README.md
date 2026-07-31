# aieng-bot Slack Agent

Slack agent for the Vector Institute workspace, built on Slack Bolt +
Socket Mode. Designed to grow into a Claude Tag-style teammate one
capability at a time.

## Architecture

```
Slack event (mention, DM, channel message, slash command)
  → Socket Mode (outbound WebSocket: no public URL, no inbound firewall rules)
  → handlers.py routes the event
      · channel messages: recorded into per-thread ContextStore (context.py)
      · mentions and DMs: handed to the Orchestrator
  → Orchestrator (agents/orchestrator.py) picks a specialist sub-agent
  → sub-agent runs its own LLM loop, streaming into a StreamingReply (streaming.py)
      · placeholder reply posted in-thread, then edited in place (throttled)
      · muted status line while working, final answer + context footer when done
  → markdown converted to Slack mrkdwn (mrkdwn.py)
```

Every Slack thread and DM gets an isolated context keyed by
`(channel, thread_ts)`, including its own multi-turn agent history, so
follow-up questions work per thread. The bot records messages in channels
it is invited to (background context) but only speaks when @mentioned or
DMed.

### Agent layer

The agent layer is orchestrator-shaped: `agents/orchestrator.py` owns the
roster of specialist sub-agents and routes each request to one of them.
With a single sub-agent registered the route is direct; when more land,
`Orchestrator.route()` becomes the dispatch point (heuristics or a small
classifier over the sub-agents' descriptions) with no change to the Slack
plumbing or the sub-agents.

| Sub-agent | Module | Status |
|---|---|---|
| bookstack: answers documentation questions from the Vector wiki | `agents/bookstack/` | live |

New sub-agents implement the `SubAgent` protocol (`agents/base.py`) and
register in `agents/__init__.py`.

The bookstack sub-agent fully owns the QA stack (`agents/bookstack/`:
Anthropic tool-use loop, BookStack API client, tools, prompts), using the
shared model + gateway plumbing (`CLAUDE_MODEL` via `aieng_bot.config`,
`LLM_BASE_URL` + `LLM_API_KEY` bearer auth). The former web chat UI and its
FastAPI backend were retired in favor of Slack.

## Local development

From the repo root:

```bash
uv sync --group slack-agent
uv run python -m slack_agent.app
```

Configuration comes from two optional dotenv files:

- repo root `.env`: LLM + BookStack credentials (`ANTHROPIC_API_KEY` or
  `LLM_BASE_URL`/`LLM_API_KEY`, `BOOKSTACK_TOKEN_ID`, `BOOKSTACK_TOKEN_SECRET`)
- `slack_agent/.env`: `SLACK_BOT_TOKEN` (xoxb), `SLACK_APP_TOKEN` (xapp)

Without BookStack/LLM credentials the bot still runs with no agents
and says so when asked.

Note: the production bot runs on Cloud Run with a single Socket Mode
connection. Running locally at the same time means both instances receive
events and reply twice. Scale the Cloud Run service down (or accept the
double replies) while testing locally.

## Continuous deployment

`.github/workflows/deploy-slack-agent.yml` builds and deploys to Cloud Run
(project `coderd`, Toronto) on every push to `main` touching
`slack_agent/**`, `src/aieng_bot/**`, or `uv.lock`.

Required GitHub secrets:

- `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`: Slack app credentials
- `BOOKSTACK_API_KEY` (used as `LLM_API_KEY`), `LLM_BASE_URL`, `CLAUDE_MODEL`,
  `BOOKSTACK_TOKEN_ID`, `BOOKSTACK_TOKEN_SECRET`: LLM gateway and BookStack
  API credentials
- `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT`: GCP auth

The service runs exactly one always-on instance (`--min-instances=1
--max-instances=1 --no-cpu-throttling`) because Socket Mode holds a
persistent WebSocket and contexts are in-memory. The HTTP port only serves
`/health`.

## Slack app configuration

The app manifest lives in `manifest.yaml` (app: **aieng-bot**,
`A0BLK0D8Q7R`). Config changes are applied with the App Manifest API
(`apps.manifest.update`); scope changes additionally require a reinstall.
Logo assets live in `assets/`.

## Roadmap

- [x] Socket Mode plumbing with per-thread contexts and background listening
- [x] BookStack QA capability with streaming replies
- [ ] Persist thread contexts across deploys
- [ ] Use recorded channel messages as ambient context for answers
- [ ] More sub-agents: GitHub, CI failures, dashboards
- [ ] Slack "Agents & AI Apps" assistant surface (needs `assistant:write` scope + reinstall)
