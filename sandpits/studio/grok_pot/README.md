# Grok Pot

Grok Pot is the reviewed intake lane for Grok-authored proposals before they
are promoted into Fridays, Studio, KC, or system prompts.

## Purpose

- Keep Grok changes traceable without letting draft material mutate production.
- Review remote proposal branches before promoting their useful parts.
- Capture local LLM training ideas for Mistral, Gemma, DeepSeek, and other
  coding agents in one Studio sandpit.
- Route accepted lessons into KC/Studio records instead of editing archived
  placeholder docs directly.

## Promotion Rules

1. Proposal branches are fetched before review.
2. Drafts with placeholders, ellipses, or unverifiable claims stay in Grok Pot.
3. Production docs that say "tracked in Studio" are not edited on disk.
4. Accepted changes must include the target surface, reason, tests, and rollback
   path.
5. Fridays, Vortex, watchdog, and KC changes require a normal PR and green CI.

## Current Review

See `REVIEW_2026-05-09.md`.
