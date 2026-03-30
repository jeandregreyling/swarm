"""
theme_engine.py — Fridays / Seven's Swarm
═══════════════════════════════════════════════════════════════════════════════
Theme injection layer. Separates Fridays look-and-feel from core terminal.py.

- Loads fridays.json (color palettes, animations, spacing)
- Detects time-of-day (auto mode)
- Manages user preferences (session / persistent)
- Injects theme into terminal_base.html at render time
- terminal.py NEVER touches theme code again

Usage:
  from theme_engine import get_themed_html
  html = get_themed_html()  # Returns fully themed + injected HTML
═══════════════════════════════════════════════════════════════════════════════
"""

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
import sys


class ThemeEngine:
    """Responsible for loading, managing, and injecting themes."""

    def __init__(self):
        self.swarm_root = Path('/home/seven/swarm')
        self.themes_dir = self.swarm_root / 'themes'
        self.templates_dir = self.swarm_root / 'frontend' / 'templates'
        
        # Ensure themes directory exists
        self.themes_dir.mkdir(exist_ok=True)
        
        # Cache loaded themes
        self._theme_cache = {}
        
        # User preference (session + default)
        self.user_theme = None  # Will be set via set_user_theme()
        self.user_time_of_day = None  # Will be set via set_time_of_day()
    
    def load_theme(self, theme_name='fridays'):
        """Load theme JSON. Cached."""
        if theme_name in self._theme_cache:
            return self._theme_cache[theme_name]
        
        theme_path = self.themes_dir / f'{theme_name}.json'
        if not theme_path.exists():
            raise FileNotFoundError(f"Theme not found: {theme_path}")
        
        with open(theme_path, 'r') as f:
            theme_data = json.load(f)
        
        self._theme_cache[theme_name] = theme_data
        return theme_data
    
    def get_current_time_of_day(self):
        """Auto-detect time of day. Return: 'morning', 'afternoon', 'evening', 'night'."""
        if self.user_time_of_day:  # User override
            return self.user_time_of_day
        
        hour = datetime.now().hour
        if 6 <= hour < 12:
            return 'morning'
        elif 12 <= hour < 17:
            return 'afternoon'
        elif 17 <= hour < 21:
            return 'evening'
        else:
            return 'night'
    
    def set_user_theme(self, theme_name):
        """Set user's preferred theme (session or persistent)."""
        self.user_theme = theme_name
    
    def set_time_of_day(self, time_period):
        """Override auto time-of-day detection. None = auto."""
        self.user_time_of_day = time_period
    
    def get_css_variables(self, theme_name='fridays'):
        """Extract CSS custom properties from theme.
        
        Returns:
            dict of CSS var assignments (--name: value;)
        """
        theme = self.load_theme(theme_name)
        
        # Start with base colors (always present)
        css_vars = {}
        
        # Extract root-level colors
        if 'colors' in theme:
            css_vars.update(theme['colors'])
        
        # Apply time-of-day overrides
        time_period = self.get_current_time_of_day()
        if 'time_of_day' in theme and time_period in theme['time_of_day']:
            css_vars.update(theme['time_of_day'][time_period])
        
        return css_vars
    
    def build_css_string(self, css_vars):
        """Convert CSS var dict to :root { ... } CSS string."""
        lines = [':root {']
        for key, value in css_vars.items():
            lines.append(f'  {key}: {value};')
        lines.append('}')
        return '\n'.join(lines)
    
    def get_theme_css(self, theme_name='fridays'):
        """Return complete theme CSS (to inject into <style> tag)."""
        theme = self.load_theme(theme_name)
        
        # CSS variables block
        css_vars = self.get_css_variables(theme_name)
        css_string = self.build_css_string(css_vars)
        
        # Theme-specific CSS (animations, layout rules, etc.)
        theme_css = theme.get('custom_css', '')
        
        return f"{css_string}\n\n{theme_css}"
    
    def get_theme_js(self, theme_name='fridays'):
        """Return theme-specific JavaScript (to inject before </body>)."""
        theme = self.load_theme(theme_name)
        return theme.get('custom_js', '')
    
    def get_time_wizard_data(self):
        """Fetch Time Wizard sessions, events, and statistics."""
        try:
            sys.path.insert(0, '/home/seven/swarm/core')
            from time_machine import time_wizard

            # Backward-compatible calls for deployments where method signatures differ.
            try:
                sessions = time_wizard.get_sessions(limit=5)
            except TypeError:
                sessions = time_wizard.get_sessions()
            try:
                events = time_wizard.get_timeline(limit=10)
            except TypeError:
                events = time_wizard.get_timeline()
            checkpoints = time_wizard.list_checkpoints()
            stats = {
                'total_sessions': len(sessions),
                'total_events': len(events),
                'total_checkpoints': len(checkpoints),
                'agents': ['twelve', 'ghost', 'nine']
            }
            
            return {
                'sessions': sessions,
                'events': events,
                'checkpoints': checkpoints,
                'stats': stats,
                'ok': True
            }
        except Exception as e:
            return {
                'sessions': [],
                'events': [],
                'checkpoints': [],
                'stats': {'total_sessions': 0, 'total_events': 0, 'total_checkpoints': 0},
                'ok': False,
                'error': str(e)
            }
    
    def get_time_wizard_js(self):
        """Generate JavaScript with Time Wizard data baked in."""
        tw_data = self.get_time_wizard_data()
        
        # Create global window variable with Time Wizard data
        js_code = f"""
// TIME WIZARD DATA (baked into template)
window._timeWizardData = {json.dumps(tw_data)};

// Load Time Wizard data on page init
function initTimeWizardData() {{
    if (window._timeWizardData && window._timeWizardData.ok) {{
        console.log('[TimeWizard] Data loaded:', window._timeWizardData);
        // Load into time-wizard UI components
        if (typeof renderTwTimeline === 'function') {{
            const decisions = window._timeWizardData.stats || [];
            renderTwTimeline(decisions);
        }}
    }}
}}

// Auto-init on DOMContentLoaded
if (document.readyState === 'loading') {{
    document.addEventListener('DOMContentLoaded', initTimeWizardData);
}} else {{
    initTimeWizardData();
}}
"""
        return js_code

    def get_alm_data(self):
        """Fetch ALM governance state for theme-layer baked injection."""
        require_approvals = os.environ.get('ALM_REQUIRE_APPROVALS', '1') == '1'

        time_wizard_active = False
        try:
            sys.path.insert(0, '/home/seven/swarm/core')
            from time_machine import time_wizard
            try:
                time_wizard_active = bool(time_wizard.get_sessions(limit=1))
            except TypeError:
                time_wizard_active = bool(time_wizard.get_sessions())
        except Exception:
            time_wizard_active = False

        counts = {'total': 0, 'pending': 0, 'approved': 0, 'executed': 0}
        try:
            conn = sqlite3.connect('/home/seven/swarm/swarm_memory.db')
            conn.row_factory = sqlite3.Row
            table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='work_proposals'"
            ).fetchone()
            if table:
                rows = conn.execute(
                    "SELECT status, COUNT(*) AS c FROM work_proposals GROUP BY status"
                ).fetchall()
                for r in rows:
                    status = (r['status'] or '').lower()
                    c = int(r['c'])
                    counts['total'] += c
                    if status in counts:
                        counts[status] += c
            conn.close()
        except Exception:
            pass

        return {
            'ok': True,
            'status': 'enforced' if (require_approvals and time_wizard_active) else 'warn',
            'alm_require_approvals': require_approvals,
            'time_wizard_active': time_wizard_active,
            # Theme layer cannot authoritatively read runtime disable list; UI can refine via /api/alm/status.
            'sniffles_enabled': None,
            'work_proposals': counts,
        }

    def get_alm_js(self):
        """Generate JavaScript with ALM governance data baked in for all themed renders."""
        alm_data = self.get_alm_data()
        js_code = f"""
// ALM GOVERNANCE DATA (baked into template by theme_engine)
window._almData = {json.dumps(alm_data)};

function _applyALMVisibility(data) {{
    const stat = document.getElementById('stat-alm');
    if (stat) {{
        stat.textContent = data.status === 'enforced' ? 'ON' : 'WARN';
        const card = stat.closest('.stat-card');
        if (card) card.className = 'stat-card ' + (data.status === 'enforced' ? 'health-good' : 'health-warn');
    }}

    const gov = document.getElementById('studio-governance');
    if (gov) {{
        const sn = data.sniffles_enabled === null ? 'checking...' : (data.sniffles_enabled ? 'enabled' : 'disabled');
        gov.innerHTML = 'ALM: <strong>' + (data.status === 'enforced' ? 'enforced' : 'warn') + '</strong> · ' +
                        'Sniffles: <strong>' + sn + '</strong> · ' +
                        'Pending: <strong>' + ((data.work_proposals && data.work_proposals.pending) || 0) + '</strong>';
    }}

    const monitor = document.getElementById('monitor-alm-status');
    if (monitor) {{
        const badge = data.status === 'enforced'
          ? '<span style="padding:2px 8px;border-radius:10px;background:#4caf5020;color:#4caf50;border:1px solid #4caf5060;font-size:10px;font-weight:700;">ENFORCED</span>'
          : '<span style="padding:2px 8px;border-radius:10px;background:#ffa50022;color:#ffa500;border:1px solid #ffa50055;font-size:10px;font-weight:700;">WARN</span>';
        monitor.innerHTML = '<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">' +
                            '<div style="font-weight:600;">ALM Governance</div>' + badge + '</div>' +
                            '<div style="font-size:11px;color:var(--text-dim);margin-top:6px;">' +
                            'Time Wizard: <strong>' + (data.time_wizard_active ? 'active' : 'inactive') + '</strong> · ' +
                            'Queue: <strong>' + ((data.work_proposals && data.work_proposals.pending) || 0) + '</strong> pending / ' +
                            '<strong>' + ((data.work_proposals && data.work_proposals.executed) || 0) + '</strong> executed' +
                            '</div>';
    }}
}}

function initALMData() {{
    if (window._almData) _applyALMVisibility(window._almData);

    // Refine baked data from authoritative runtime endpoint when available.
    if (typeof fetch === 'function') {{
        fetch('/api/alm/status')
          .then(r => r.json())
          .then(d => {{ if (d && d.ok) {{ window._almData = d; _applyALMVisibility(d); }} }})
          .catch(() => {{}});
    }}
}}

if (document.readyState === 'loading') {{
    document.addEventListener('DOMContentLoaded', initALMData);
}} else {{
    initALMData();
}}

// Refresh ALM state at low frequency; avoid mutation-observer loops that can
// overload browsers during heavy DOM updates.
if (!window.__almPollTimer) {{
    window.__almPollTimer = setInterval(() => initALMData(), 30000);
}}
"""
        return js_code
    
    def render_html(self, theme_name='fridays', template='terminal_base.html'):
        """Load a template, inject theme + Time Wizard data, return fully themed HTML.
        Theme cache is flushed on each render so time-of-day shifts apply live
        without a service restart.
        """
        # Always reload theme from disk so time-of-day changes take effect
        self._theme_cache.pop(theme_name, None)
        template_path = self.templates_dir / template
        
        if not template_path.exists():
            raise FileNotFoundError(f"Base template not found: {template_path}")
        
        with open(template_path, 'r') as f:
            html = f.read()
        
        # Get theme CSS & JS
        theme_css = self.get_theme_css(theme_name)
        theme_js = self.get_theme_js(theme_name)
        time_wizard_js = self.get_time_wizard_js()
        alm_js = self.get_alm_js()
        
        # Inject into placeholders
        html = html.replace('{{ theme_css }}', theme_css)
        html = html.replace('{{ theme_js }}', theme_js)
        
        # Inject governance + time data into script tags before </body>
        time_wizard_script = f'<script>{time_wizard_js}</script>'
        alm_script = f'<script>{alm_js}</script>'
        html = html.replace('</body>', f'{time_wizard_script}\n{alm_script}\n</body>')
        
        return html


# Global instance
_engine = None

def get_engine():
    """Get or create the singleton theme engine."""
    global _engine
    if _engine is None:
        _engine = ThemeEngine()
    return _engine

def get_themed_html(theme_name='fridays', template='terminal_base.html'):
    """Convenience function. Returns fully themed & injected HTML."""
    engine = get_engine()
    return engine.render_html(theme_name, template)

def set_user_theme(theme_name):
    """Set user's theme for this session."""
    engine = get_engine()
    engine.set_user_theme(theme_name)

def set_time_of_day(time_period):
    """Override auto time-of-day detection."""
    engine = get_engine()
    engine.set_time_of_day(time_period)
