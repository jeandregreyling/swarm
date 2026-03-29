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
            
            sessions = time_wizard.get_sessions(limit=5)
            events = time_wizard.get_timeline(limit=10)
            checkpoints = time_wizard.list_checkpoints()
            stats = {
                'total_sessions': len(time_wizard.get_sessions()),
                'total_events': len(time_wizard.get_timeline()),
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
        
        # Inject into placeholders
        html = html.replace('{{ theme_css }}', theme_css)
        html = html.replace('{{ theme_js }}', theme_js)
        
        # Inject Time Wizard data into a script tag before </body>
        time_wizard_script = f'<script>{time_wizard_js}</script>'
        html = html.replace('</body>', f'{time_wizard_script}\n</body>')
        
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
