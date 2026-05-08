# Watched-topic Workflow

> S-895CAA882C — Documentation for the SAP / watched-topic pipeline so
> operators don't have to read source to understand how a topic flows
> from "added in Studio" to "digest in your inbox".

## Mental model

```
Studio "Add watched topic"
        │
        ▼
watched_topic_settings           ← cadence + digest mode
        │  topic_key
        ▼
Tasker scheduled_tasks           ← link via project_step_id
        │  fires every cadence
        ▼
fridays.task_runner.watched_topic
        │  search → score → dedupe
        ▼
watched_topic_evidence           ← rows tagged is_historical=0/1
        │
        ▼
core.watched_topics              ← confidence_band + render_summary
        │
        ▼
notifications                    ← email / Discord / UI card
```

## Key surfaces

| Surface | Module | Purpose |
| --- | --- | --- |
| UX copy | `core.watched_topics.UX_COPY` / `copy_for(key, **ctx)` | Single source of truth for empty-state, run-now, confidence labels. (S-A8032C5016) |
| Confidence band | `core.watched_topics.confidence_band(score)` | Maps 0..1 → `low` / `borderline` / `high`. (S-AA5F5A23C0) |
| Notify gate | `core.watched_topics.should_notify(score)` | Returns `True` only for borderline+high. |
| Seed baseline | `core.watched_topics.seed_baseline_for(topic_key)` | Rows the watcher should INSERT on first activation so day-one isn't a spam wall. (S-A60F04117B) |
| Summary template | `core.watched_topics.render_summary(...)` | Plain-text digest used by email + Discord + Studio cards. (S-3AF5EBCF59) |
| Manual-run payload | `core.watched_topics.manual_run_payload(topic_key)` | Shape the Studio "Run now" button POSTs to Tasker. (S-C97E117533) |

## Data tables

* `watched_topic_settings(topic_key, digest_mode, digest_period_hours,
  cadence_minutes, ...)` — per-topic cadence + digest-vs-instant mode.
* `watched_topic_evidence(topic_key, evidence_url, score, recency_label,
  recency_score, review_status, review_note, is_historical, ...)` —
  scoring memory; `is_historical=1` rows are baseline/seed anchors.
* `scheduled_tasks(.., project_id, project_step_id, missed_run_policy)` —
  task that fires the watcher on cadence; links back to a project step.
* `project_step_evidence` — auto-created when a step-linked task fires
  so closeout sees real evidence per cadence.

## Operator runbook

### Add a topic

1. Studio → Tasker → "Add watched topic".
2. Pick `topic_key` (lowercase, dash/underscore separators).
3. Choose cadence (default 24h digest) and confidence floor (default
   uses `core.watched_topics.confidence_band`).
4. On first save, the watcher calls `seed_baseline_for(topic_key)` and
   inserts the returned rows so dedupe has anchors.

### Run now

* Studio card "Run now" button POSTs `manual_run_payload(topic_key)` to
  `/api/tasker/run-now`.
* The handler wraps the run with `utils.tasker_run_lock.try_run` so
  rapid clicks can't fire the watcher twice in parallel
  (S-941A9C1A0A).
* Result toast uses `copy_for("manual_run_done", new_count=…,
  updated_count=…, skipped_count=…)`.

### Tuning thresholds

* Confidence cutoffs live in `CONFIDENCE_BANDS` (single list at the top
  of `core/watched_topics.py`). Edit there, run
  `tests/test_watched_topics_helpers.py`, ship.

### Disabling a topic

* Set `digest_mode='off'` in `watched_topic_settings` or remove the
  scheduled task. Existing evidence rows stay so re-enabling doesn't
  lose history.

## Closeout / audit trail

* Each task fire writes one row into `project_step_evidence` if the
  task is linked to a project step (S-F4DC817B17).
* `core.knowledge.close_out.build_report` includes those evidence rows
  in the per-step view; the markdown export (S-4DB57C3A23) renders
  them under each step.

## Failure modes

| Symptom | Cause | Fix |
| --- | --- | --- |
| No hits for an active topic | Sources blocked by CI no-network profile | Disable via `utils.ci_profile.disable_no_network()` for prod runs. |
| Two watcher runs at once | Stale UI state pressing "Run now" twice | Already gated by `tasker_run_lock`. |
| Empty digest emails | `should_notify(score)` returned `False` for every hit | Check `confidence_band` cutoffs; raise `digest_period_hours` so a window batches more candidates. |
| First-day spam | `seed_baseline_for` rows not inserted | Re-add the topic; the seed insert is idempotent on `topic_key`. |
