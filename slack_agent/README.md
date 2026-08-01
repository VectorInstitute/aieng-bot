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
      · mentions: question wrapped with an ambient window of recent channel
        and thread messages (slack_context.py) on the session's first turn
      · mentions and DMs: handed to the Orchestrator
  → Orchestrator (agents/orchestrator.py) picks a specialist sub-agent
      · sticky per-thread sessions, keyword scoring for fresh ones
  → sub-agent runs its own LLM loop, streaming into a StreamingReply (streaming.py)
      · tools: BookStack (search, get_page) or GitHub (repos, code, PRs,
        issues, CI) + Slack history on demand
        (agents/slack_tools.py; bound to the current channel)
      · native plan block while working, final answer + context footer when done
  → markdown converted to Slack mrkdwn (mrkdwn.py)
```

Design specs for the context layer live in `docs/DESIGN.md`, with the
architecture diagram in `docs/aieng-bot-slack-architecture.drawio`.

Every Slack thread and DM gets an isolated context keyed by
`(channel, thread_ts)`, including its own multi-turn agent history, so
follow-up questions work per thread. The bot records messages in channels
it is invited to (background context) but only speaks when @mentioned or
DMed.

### Agent layer

The agent layer is orchestrator-shaped: `agents/orchestrator.py` owns the
roster of specialist sub-agents and routes each request to one of them.
Routing is sticky per thread session (follow-ups stay with the agent that
answered); fresh sessions are scored against each sub-agent's `keywords`
hints, falling back to the first registered agent.

| Sub-agent | Module | Status |
|---|---|---|
| bookstack: answers documentation questions from the Vector wiki | `agents/bookstack/` | live |
| github: answers questions about VectorInstitute repos, code, PRs, issues, CI (read-only) | `agents/github/` | live |

New sub-agents implement the `SubAgent` protocol (`agents/base.py`) and
register in `agents/__init__.py`. The Anthropic tool-use loop (streaming,
thinking-model handling, tool dispatch) is shared in `agents/toolloop.py`;
each sub-agent binds it to its own API client, tools, and prompts, using
the shared model + gateway plumbing (`CLAUDE_MODEL` via `aieng_bot.config`,
`LLM_BASE_URL` + `LLM_API_KEY` bearer auth).

GitHub credentials are read-only by construction: preferably a GitHub App
(`GITHUB_APP_ID` + private key) whose installation tokens carry only the
app's read permissions, or a fine-grained read-only PAT (`GITHUB_TOKEN`)
for local dev. All lookups are pinned to `GITHUB_ORG` (default
VectorInstitute) inside the client, so the model cannot reach other
owners.

## Local development

From the repo root:

```bash
uv sync --group slack-agent
uv run python -m slack_agent.app
```

Configuration comes from two optional dotenv files:

- repo root `.env`: LLM + BookStack + GitHub credentials
  (`ANTHROPIC_API_KEY` or `LLM_BASE_URL`/`LLM_API_KEY`,
  `BOOKSTACK_TOKEN_ID`, `BOOKSTACK_TOKEN_SECRET`, and either
  `GITHUB_APP_ID` + `GITHUB_APP_PRIVATE_KEY_FILE` (path to the
  downloaded `.pem`, optionally `GITHUB_APP_INSTALLATION_ID`) or a
  read-only `GITHUB_TOKEN`)
- `slack_agent/.env`: `SLACK_BOT_TOKEN` (xoxb), `SLACK_APP_TOKEN` (xapp)

Sub-agents enable independently: missing credentials disable that
sub-agent (logged at startup), and with none configured the bot still
runs and says so when asked.

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
- `ORG_ACCESS_TOKEN` (passed as `GITHUB_TOKEN`): interim credential for
  the github sub-agent. The token is write-capable, but the agent's
  tool roster is read-only and org-pinned, so writes cannot happen
  through the agent; swap to the App credentials below to make the
  credential itself read-only.
- `GH_APP_ID`, `GH_APP_INSTALLATION_ID`, `GH_APP_PRIVATE_KEY_B64`
  (base64 of the `.pem`, newline-safe for `--set-env-vars`): read-only
  GitHub App credentials; when set they take precedence over
  `GITHUB_TOKEN`
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
- [x] Ambient channel context + on-demand Slack history tools
- [x] GitHub sub-agent (read-only: repos, code search, PRs, issues, CI)
- [ ] More sub-agents: CI failure fixing, dashboards
- [ ] GitHub write capabilities (behind the `write` access tier + org-owned App)
- [ ] Slack "Agents & AI Apps" assistant surface (needs `assistant:write` scope + reinstall)
