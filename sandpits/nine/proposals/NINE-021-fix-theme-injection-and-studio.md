# Proposal: Fix Theme Injection + Studio CSS Variables
**Agent:** Nine (System Architect)
**Date:** 2026-03-29
**Status:** EXECUTED
**Proposal ID:** NINE-021

---

## Root Causes Found

### Bug 1 — Theme injection order is backwards (theme never applies)
`terminal_ui_v2.html` line 9: `{{ theme_css }}` is injected FIRST inside `<style>`.
The hardcoded `:root {}` fallback block follows at line 24.
In CSS, later `:root {}` rules with equal specificity win — so the fallback PERMANENTLY
overrides the theme injection. The theme engine runs, injects CSS, and it is silently
discarded every time. Night theme, morning theme — none of them ever took effect.

Fix: Move `{{ theme_css }}` to AFTER the `:root {}` fallback block.

### Bug 2 — `fridays.json` uses wrong CSS variable names
The JSON defines `--color-primary`, `--color-bg`, `--color-text`, `--color-accent`,
`--color-border`, `--color-secondary`. The template uses `--bg`, `--text`, `--accent`,
`--border`, `--card`, `--text-dim`, `--hover`. Zero overlap. Even if the injection order
were correct, no theme variable would match anything in the CSS.

Fix: Rewrite `fridays.json` to use the exact variable names the template uses.

### Bug 3 — `--hover` and `--bg-input` undefined everywhere
Studio CSS uses `var(--hover)` for button backgrounds, chat bubbles, context panel
backgrounds. `--hover` is not in the `:root` fallback, not in fridays.json, nowhere.
Every Studio element using it renders transparent or invisible.

Fix: Add `--hover` and `--bg-input` to the `:root` fallback.

---

## Changes

| File | Change |
|------|--------|
| `frontend/templates/terminal_ui_v2.html` | Move `{{ theme_css }}` after `:root` block; add `--hover` and `--bg-input` to `:root` |
| `themes/fridays.json` | Rewrite with correct variable names + 4 proper time-of-day palettes |
