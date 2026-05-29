# BlahajAI 🦈

A cozy little fork of [Hermes Agent](https://github.com/NousResearch/hermes-agent), maintained by **BlahajBot** for Latte's local-first agent setup.

This repo tracks the Hermes codebase plus the local patches that make the shark feel at home: Discord-first workflow, warm Blåhaj-flavored personality, practical sysadmin autonomy, and careful tooling for self-hosted AI work.

## What this fork is for

- keeping the BlåhajBot deployment reproducible
- preserving local Hermes patches in a real GitHub remote
- experimenting with agent UX, safety checks, gateway behavior, and tool ergonomics
- staying close enough to upstream Hermes that merges remain manageable

## Interesting differences from upstream

BlahajAI is intentionally close to upstream Hermes, but it carries a few local patches that are useful for this deployment. Compare against the shared merge base for the meaningful fork delta; comparing against the newest upstream `main` can look much larger simply because upstream moves fast.

### BlåhajBot-facing repo shape

- The landing README is this short fork-specific overview.
- The original Hermes README is preserved as [`README.upstream.md`](README.upstream.md).
- The fork keeps Latte's local deployment patches in a public, reproducible remote rather than only on the running machine.

### Brave Search toolset

- Adds `brave_web_search` and `brave_news_search` tools backed by the Brave Search API.
- Adds a dedicated `brave` toolset and wires the Brave tools into Hermes tool discovery.
- Useful for current web/news search when the deployment has a Brave API key configured.

### Groq text-to-speech

- Adds a Groq TTS provider path using `GROQ_API_KEY`.
- Includes Groq model, voice, and base URL configuration handling.
- Keeps fast hosted TTS available as an option alongside the other Hermes TTS providers.

### Smart command approval work

- Adds deterministic auto-approval for narrow low-risk command shapes to reduce approval fatigue.
- Keeps LLM-backed smart approval for ambiguous cases, but requires structured JSON decisions: `approve`, `deny`, or `escalate`.
- Adds compact execution context for the approval judge, including working directory and referenced path summaries.
- Emits visible smart-approval audit/progress messages so approvals are easier to inspect after the fact.

### Terminal approval UX

- Terminal results include clearer approval notes for user-approved, smart-approved, smart-denied, deterministic auto-approved, and smart-escalated commands.
- Workdir validation happens before smart approval context is built, so approval decisions are based on the actual execution location.

### `/spark` one-shot lane

- Adds a text-only `/spark <prompt>` lane for quick isolated calls to `gpt-5.3-codex-spark`.
- Avoids normal session history and channel prompt context for that one-shot route.
- Keeps spark prompts as plain text commands in Discord/gateway handling.

### Discord and personality compatibility

- Carries local Discord behavior patches for the BlåhajBot deployment.
- Preserves personality-selection state fixes used by the running agent.
- Includes compatibility patches around gateway session keys, cron toolsets, and newer tool dispatch APIs.

### Image and media handling tweaks

- Adds per-call OpenAI image quality selection so callers can choose draft vs higher-quality renders without changing global config.
- Keeps local patches around Codex image input references and image editing support labels.
- Carries gateway video attachment support with metadata extraction and thumbnails.

### Provider and memory safety fixes

- Hardens some Anthropic request-build error handling.
- Avoids a Honcho memory-file migration behavior that could duplicate memory in this deployment.

## Upstream

The original project is Nous Research's Hermes Agent. The upstream README is preserved here as [`README.upstream.md`](README.upstream.md).

## Vibe

Technically sharp, cozy by default, and just a little shark-coded.
