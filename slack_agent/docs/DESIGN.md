# aieng-bot Slack Agent: Context Layer Design

Status: v1, July 31 2026. Companion diagram: `aieng-bot-slack-architecture.drawio`.

## Goal

Make aieng-bot channel-aware the way Claude Tag is: when tagged in a
channel it should already understand the recent conversation, and it
should be able to reach deeper into history on its own when a question
demands it, without flooding the model's context window (and KV cache)
with everything upfront.

## Reference model (Claude Tag)

From Anthropic's docs and third-party writeups, Claude Tag's context
model has three layers:

1. **Thread session**: each thread is a working session. Mentioning
   Claude mid-thread gives it up to ~50 messages from the start of the
   thread. Anyone in the thread can steer without re-mentioning.
2. **Channel context**: it follows along in channels it has joined and
   can search and read channel history while working on a task, not
   only what was pushed into the prompt.
3. **Memory**: per-channel notes that persist across sessions; public
   channel memory is shared workspace-wide, private stays local.

It responds when mentioned; unprompted (ambient) replies exist but are
conservative and self-throttling.

## Context layers for aieng-bot

| Layer | What | Status |
|---|---|---|
| L1 Thread session | Per-(channel, thread_ts) multi-turn agent history, per-thread lock | Live since 0.2.0 |
| L2 Ambient window | Small recent-message window (channel + pre-mention thread) injected once when a thread session starts | This design |
| L3 On-demand history tools | Slack Web API exposed to the model as tools (like the BookStack tools) so it pulls more history only when needed | This design |
| L4 Memory | Persistent per-channel notes, workspace sharing | Future |
| L5 Ambient replies | Answering without a mention when confident | Future, deliberately conservative |

### Why L2 + L3 instead of stuffing history

Pushing hundreds of messages into every request wastes tokens, bloats
the KV cache, and buries the question. The split mirrors how Claude
Tag behaves and how the BookStack capability already works:

- **L2** guarantees the model always sees the immediate conversational
  frame (what was just said, who is asking, what thread it is in) at a
  fixed small cost (~15 channel messages + up to 20 thread replies,
  each truncated).
- **L3** turns "more context" into a model decision: the agent calls
  `get_channel_history` / `get_thread_replies` exactly when the
  question references something outside the window ("what did we
  decide about X last week?"), the same way it calls
  `search_bookstack` only when it needs the wiki.

### Interaction rules (unchanged)

- **Channels**: the bot records messages it can see (background
  listening) but speaks only when @mentioned. L5 may relax this later.
- **DMs**: one rolling inline conversation per person (replies go in
  the main flow, not forced threads; explicit threads are respected and
  get their own session). Ambient window does not apply. Session
  history is capped, cut only at plain user-turn boundaries so
  tool-call pairs never split.
- **Silence**: the model may decline to reply (NO_REPLY protocol): the
  placeholder is deleted and only a quiet reaction lands on the user's
  message, which is what a human does when told "no need to respond".
- Thread follow-ups: mentioning the bot again in the same thread
  continues the session with full history (L1).

## Architecture

```
Slack event (mention in channel)
  → handlers.py
      1. resolve thread context (L1) from ContextStore
      2. if the session is new: SlackContextService builds the ambient
         window (L2) via conversations.history + conversations.replies,
         resolving user IDs to display names (cached)
      3. wrap the question: <slack_context>…</slack_context> + question
  → Orchestrator routes to the sub-agent
  → BookStack sub-agent runs the LLM loop with BOTH toolsets:
      · BookStack tools: search_bookstack, get_page, list_books
      · Slack tools (L3): get_channel_history, get_thread_replies
        (bound to the current channel only)
  → StreamingReply renders steps as a native plan block
```

### Components

- `slack_context.py`: `SlackContextService`, the single owner of Slack
  context: display-name resolution (cached, batched), message rendering
  (local-time stamps, truncation, thread markers), the ambient window,
  and `wrap_question()` (the `<slack_context>` prompt contract). Both
  L2 and the L3 tools render through this one service.
- `agents/slack_tools.py`: Anthropic tool definitions, step labels, the
  system-prompt suffix, and an async executor factory bound to
  (service, channel). Tools:
  - `get_channel_history(limit≤100, oldest?)`: recent channel messages
  - `get_thread_replies(thread_ts)`: full replies of one thread
- `agents/bookstack/agent.py`: the LLM loop accepts extra tools, an
  async extra executor (dispatch: anything outside the BookStack tool
  names), and a system suffix per call, keeping the loop generic
- `agents/bookstack/subagent.py`: composes both toolsets and their step
  labels

### Reactions (human-like emoji)

UX philosophy: instant acknowledgment beats delayed personality, and a
teammate reacts to *your* message, not their own answer.

- The 👀 ack stays mechanical: the "seen" signal must beat the model.
- At completion, the model chooses the reaction left on the asker's
  message via a ``reaction: <emoji>`` sign-off line stripped from the
  answer (zero extra turns; defaults to ✅; failures keep ⚠️).
- The ``add_reaction`` tool lets the agent react to *any* message in
  the current channel the way a person would (🎉 under a launch it read
  in history). Guardrails: channel-bound, emoji-name validation, at
  most 3 per run, and prompt guidance that most messages get none.

### Scope and safety

- Slack tools are hard-bound to the channel the question came from; the
  model cannot name another channel. Private-channel data therefore
  never crosses channels (same boundary Slack enforces on the bot).
- All Slack tool calls use the bot token and existing granted scopes
  (`channels:history`, `groups:history`, `users:read`); no new scopes,
  no reinstall.
- Ambient window budget: ≤15 channel messages + ≤20 thread replies,
  each truncated to 280 chars, total ≤6k chars.
- Tool results are truncated server-side (per message and per call) so
  a single tool call cannot blow the context.

### Failure modes

- Slack API errors in ambient building: log and continue with no
  ambient window (the mention text still carries the question).
- Slack tool errors: returned to the model as an error string (same
  convention as BookStack tools); the model can proceed without.
- Rate limits: ambient adds ≤2 Web API calls per new session;
  tools are model-initiated and bounded by the agent's MAX_TURNS.

## Rollout

1. **This change (L2 + L3)**: ambient window + Slack history tools.
   Highest value: it fixes "the bot has no idea what the channel was
   just talking about" and unlocks "what did we discuss?" questions,
   with flat token cost.
2. L4 memory: persistent channel notes (needs storage; candidates:
   Cloud Run volume, Firestore, or BookStack itself).
3. L5 ambient replies: opt-in per channel, conservative triggers.
4. Session persistence across deploys (currently in-memory).

Deliberate debt, with triggers:

- Tool-registry refactor (a `ToolLoopAgent` over composed toolsets
  instead of BookStack-primary + extras): do when a third toolset
  lands (L4 memory tools are the likely trigger).
- `SLACK_TIMEZONE` read from env at import; fold into `Settings` on
  the next config change.

## Sources

- Anthropic Claude Tag docs: how-it-works (session model, ~50-message
  thread window, channel search), users/memory
- Pluto Security, "Inside Claude Tag" (ambient replies, memory scoping)
- Slack API: conversations.history, conversations.replies, users.info
