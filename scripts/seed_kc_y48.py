"""Y.48 — Seed the Knowledge Center with curated entries for every new pillar.

Idempotent: re-running the script merges (UNIQUE-constrained) without
duplicating rows. Touches three KC surfaces:

* `kc_media_curriculum`  — topic↔tool mappings across music/image/video/style/
  genre/production AND the new `app` and `game` kinds (Y.47 App Center).
* `user_interests`       — seed topics tied to each new pillar (synth_board
  node families, video timeline tracks, App Center frameworks/targets, etc.)
  attributed to source_agent='librarian'.
* (informational)        — counts the new App Center kinds/frameworks and
  prints a summary so a human can verify coverage.

Run from repo root::

    .venv/bin/python scripts/seed_kc_y48.py
"""
from __future__ import annotations

import datetime as _dt
import os
import sqlite3
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DB = os.environ.get('SWARM_DB', os.path.join(ROOT, 'swarm_memory.db'))


# ---------------------------------------------------------------------------
# Curriculum: topic ↔ tool mappings, grouped by kind. Notes are short and
# practical — the kind a chat surface can quote when suggesting a workflow.
# ---------------------------------------------------------------------------
CURRICULUM: list[tuple[str, str, str, str]] = [
    # ── music ─────────────────────────────────────────────────────────────
    ('lo-fi beats',          'music', 'synth_board',     'arrange sampler→filter→delay→reverb chain'),
    ('lo-fi beats',          'music', 'musicgen',        'short loops, prompt with tempo + mood'),
    ('cinematic strings',    'music', 'stable_audio',    'long-form orchestral textures'),
    ('cinematic strings',    'music', 'audio_ldm',       'fine control over instrument timbre'),
    ('drum loops',           'music', 'synth_board',     'sequencer→sampler→compressor'),
    ('ambient pads',         'music', 'synth_board',     'oscillator→lfo→reverb, slow attack envelope'),
    ('vocal synthesis',      'music', 'audio_ldm',       'phoneme-aligned generation'),
    ('mastering',            'music', 'fl_studio',       'eq + compressor + limiter on master bus'),
    ('mastering',            'music', 'ableton',         'native EQ Eight + Glue Compressor'),
    # ── image ─────────────────────────────────────────────────────────────
    ('character portrait',   'image', 'flux',            'high-fidelity faces, prompt with lighting'),
    ('character portrait',   'image', 'sdxl',            'good for stylised illustration'),
    ('product mockup',       'image', 'sdxl',            'use img2img with white-bg reference'),
    ('icon set',             'image', 'stable_diffusion','tile mode + low CFG for clean shapes'),
    ('photo retouch',        'image', 'photoshop',       'curves + frequency separation'),
    ('texture',              'image', 'stable_diffusion','seamless tiling at 512×512'),
    # ── video ─────────────────────────────────────────────────────────────
    ('explainer cut',        'video', 'video_editor',    'caption track + voiceover + b-roll overlay'),
    ('explainer cut',        'video', 'davinci',         'colour grade + Fairlight audio mix'),
    ('motion graphics',      'video', 'after_effects',   'expressions for parametric animation'),
    ('text-to-video',        'video', 'runway',          'gen-3 alpha for short clips'),
    ('text-to-video',        'video', 'pika',            'good for stylised motion'),
    ('image-to-video',       'video', 'stable_video',    'works best with high-contrast inputs'),
    ('reels cut',            'video', 'video_editor',    'vertical 9:16 timeline preset'),
    # ── style / genre / production ────────────────────────────────────────
    ('cyberpunk',            'style',      'sdxl',       'neon palette + film grain LoRA'),
    ('film noir',            'style',      'flux',       'high-contrast monochrome prompts'),
    ('synthwave',            'genre',      'synth_board','saw oscillator + chorus + tape delay'),
    ('drum & bass',          'genre',      'fl_studio',  '170 bpm, reese bass, amen break'),
    ('podcast production',   'production', 'video_editor','dialogue track + noise reduction effect'),
    ('vlog production',      'production', 'davinci',    'multicam + colour match + LUT'),
    # ── app (NEW Y.47) ────────────────────────────────────────────────────
    ('mobile app',           'app',  'flutter',          'cross-platform iOS+Android from one codebase'),
    ('mobile app',           'app',  'react-native',     'JavaScript stack, large ecosystem'),
    ('mobile app',           'app',  'expo',             'fast scaffold + OTA updates'),
    ('tablet app',           'app',  'flutter',          'responsive layouts via LayoutBuilder'),
    ('desktop app',          'app',  'tauri',            'rust + webview, small bundle'),
    ('desktop app',          'app',  'electron',         'node + chromium, broad compatibility'),
    ('web app',              'app',  'next',             'react + server actions, edge deploy'),
    ('web app',              'app',  'sveltekit',        'compiled, lean bundles'),
    ('web app',              'app',  'astro',            'islands + content-first sites'),
    ('progressive web app',  'app',  'pwa',              'service worker + manifest, installable'),
    ('cross-platform',       'app',  'flutter',          'one codebase → ios/android/web/desktop'),
    ('native android',       'app',  'native-android',   'kotlin + jetpack compose'),
    ('native ios',           'app',  'native-ios',       'swift + swiftui'),
    # ── game (NEW Y.47) ───────────────────────────────────────────────────
    ('2d arcade',            'game', 'godot',            'gdscript, free, ships to web/desktop'),
    ('2d arcade',            'game', 'phaser',           'browser game, html5'),
    ('2d arcade',            'game', 'love2d',           'lua, tiny binary'),
    ('3d action',            'game', 'unity',            'c#, large asset store'),
    ('3d cinematic',         'game', 'unreal',           'c++/blueprints, AAA fidelity'),
    ('python prototype',     'game', 'pygame',           'fastest path to a playable demo'),
    ('itch.io release',      'game', 'godot',            'export web build, html5 wrapper'),
    ('steam release',        'game', 'unity',            'steamworks plugin available'),
]


# ---------------------------------------------------------------------------
# user_interests seed: high-level topics so chat surfaces and suggestion
# pickers can recommend new pillars without manual onboarding.
# ---------------------------------------------------------------------------
USER_INTERESTS: list[tuple[str, str]] = [
    # category, topic
    ('media_synth',     'synth board'),
    ('media_synth',     'oscillator'),
    ('media_synth',     'sampler'),
    ('media_synth',     'sequencer'),
    ('media_synth',     'arpeggiator'),
    ('media_video',     'video editor'),
    ('media_video',     'caption track'),
    ('media_video',     'multicam'),
    ('media_video',     'reels cut'),
    ('apps',            'mobile app'),
    ('apps',            'desktop app'),
    ('apps',            'web app'),
    ('apps',            'progressive web app'),
    ('apps',            'cross-platform'),
    ('apps_framework',  'flutter'),
    ('apps_framework',  'react-native'),
    ('apps_framework',  'tauri'),
    ('apps_framework',  'electron'),
    ('apps_framework',  'next'),
    ('apps_framework',  'sveltekit'),
    ('apps_target',     'ios'),
    ('apps_target',     'android'),
    ('apps_target',     'windows'),
    ('apps_target',     'macos'),
    ('apps_target',     'linux'),
    ('apps_target',     'web'),
    ('apps_target',     'wasm'),
    ('games',           '2d arcade'),
    ('games',           '3d action'),
    ('games',           '3d cinematic'),
    ('games',           'python prototype'),
    ('games_engine',    'godot'),
    ('games_engine',    'unity'),
    ('games_engine',    'unreal'),
    ('games_engine',    'phaser'),
    ('games_platform',  'itch.io'),
    ('games_platform',  'steam'),
]

USER = 'seven'              # default profile owner for seed interests
SOURCE_AGENT = 'librarian'  # provenance for these rows
SEED_SCORE = 8.0            # below user-entered (10.0) so it's secondary


def _ensure_curriculum_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS kc_media_curriculum (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            kind  TEXT NOT NULL,
            tool  TEXT NOT NULL,
            notes TEXT,
            created_at REAL NOT NULL,
            UNIQUE(topic, kind, tool)
        )"""
    )


def _ensure_user_interests_table(conn: sqlite3.Connection) -> None:
    # Mirrors utils/db/_schema.py but is safe if the schema bootstrap hasn't run.
    conn.execute(
        """CREATE TABLE IF NOT EXISTS user_interests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL DEFAULT 'ghost',
            topic TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            source TEXT DEFAULT 'user',
            source_agent TEXT DEFAULT '',
            score REAL DEFAULT 10.0,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(username, topic)
        )"""
    )


def seed_curriculum(conn: sqlite3.Connection) -> tuple[int, int]:
    """Returns (inserted, merged) counts."""
    inserted = merged = 0
    now = time.time()
    for topic, kind, tool, notes in CURRICULUM:
        try:
            conn.execute(
                "INSERT INTO kc_media_curriculum (topic, kind, tool, notes, created_at) "
                "VALUES (?,?,?,?,?)",
                (topic, kind, tool, notes, now),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            conn.execute(
                "UPDATE kc_media_curriculum SET notes=? WHERE topic=? AND kind=? AND tool=?",
                (notes, topic, kind, tool),
            )
            merged += 1
    conn.commit()
    return inserted, merged


def seed_user_interests(conn: sqlite3.Connection) -> tuple[int, int]:
    inserted = merged = 0
    now = _dt.datetime.now(_dt.UTC).strftime('%Y-%m-%d %H:%M:%S')
    for category, topic in USER_INTERESTS:
        try:
            conn.execute(
                "INSERT INTO user_interests (username, topic, category, source, source_agent, score, active, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (USER, topic, category, 'seed', SOURCE_AGENT, SEED_SCORE, 1, now, now),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            conn.execute(
                "UPDATE user_interests SET category=?, source_agent=?, updated_at=? "
                "WHERE username=? AND topic=?",
                (category, SOURCE_AGENT, now, USER, topic),
            )
            merged += 1
    conn.commit()
    return inserted, merged


def main(db_path: str = DB) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        _ensure_curriculum_table(conn)
        _ensure_user_interests_table(conn)
        c_ins, c_mrg = seed_curriculum(conn)
        u_ins, u_mrg = seed_user_interests(conn)
        # Counts for summary
        total_curr = conn.execute("SELECT COUNT(*) FROM kc_media_curriculum").fetchone()[0]
        total_int = conn.execute("SELECT COUNT(*) FROM user_interests WHERE source='seed'").fetchone()[0]
        kinds = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT kind, COUNT(*) FROM kc_media_curriculum GROUP BY kind"
            ).fetchall()
        }
        result = {
            'ok': True,
            'curriculum': {'inserted': c_ins, 'merged': c_mrg, 'total': total_curr,
                            'by_kind': kinds},
            'user_interests': {'inserted': u_ins, 'merged': u_mrg, 'seed_total': total_int},
        }
        return result
    finally:
        conn.close()


if __name__ == '__main__':
    out = main()
    print('Y.48 KC seed result:')
    for k, v in out.items():
        print(f'  {k}: {v}')
    sys.exit(0)
