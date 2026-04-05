// Theme engine, settings, world clocks
// Extracted from terminal_base.html

// ═══════════════════════════════════════════════════════════════════════════
// TIME-OF-DAY & SETTINGS MANAGER
// ═══════════════════════════════════════════════════════════════════════════

function getTimeOfDay() {
  const hour = new Date().getHours();
  if (hour >= 6 && hour < 12) return 'morning';
  if (hour >= 12 && hour < 18) return 'afternoon';
  if (hour >= 18 && hour < 22) return 'evening';
  return 'night';
}

// Color palettes — time-of-day + named premium themes
const TIME_PERIOD_COLORS = window._fridays && window._fridays.time_of_day
  ? window._fridays.time_of_day
  : {
  morning: {
    '--bg': '#fff8ef',
    '--card': '#ffffff',
    '--card-hover': '#fff3df',
    '--border': '#f0ddc3',
    '--text': '#2f271b',
    '--text-dim': '#897257',
    '--accent': '#e89242',
    '--accent-hover': '#f0a562',
    '--window-bg': '#fffdf9',
    '--window-header': '#fff2df',
    '--radius': '8px',
    '--shadow': '0 8px 32px rgba(80,40,0,0.10)',
  },
  afternoon: {
    '--bg': '#edf3ff',
    '--card': '#ffffff',
    '--card-hover': '#f2f7ff',
    '--border': '#d6e0ef',
    '--text': '#13243b',
    '--text-dim': '#617590',
    '--accent': '#2f6bff',
    '--accent-hover': '#5486ff',
    '--window-bg': '#ffffff',
    '--window-header': '#f1f6ff',
    '--radius': '8px',
    '--shadow': '0 8px 32px rgba(20,50,100,0.10)',
  },
  evening: {
    '--bg': '#161229',
    '--card': '#241b3e',
    '--card-hover': '#2e2250',
    '--border': '#4a3a6c',
    '--text': '#efe8ff',
    '--text-dim': '#b4a4d4',
    '--accent': '#c286ff',
    '--accent-hover': '#d19bff',
    '--window-bg': '#1f1737',
    '--window-header': '#151028',
    '--radius': '10px',
    '--shadow': '0 20px 60px rgba(0,0,0,0.6)',
  },
  night: {
    '--bg': '#0e1523',
    '--card': '#162033',
    '--card-hover': '#1d2a42',
    '--border': '#2f466b',
    '--text': '#e4efff',
    '--text-dim': '#93a9c9',
    '--accent': '#6aa4ff',
    '--accent-hover': '#88b8ff',
    '--window-bg': '#121d30',
    '--window-header': '#0c1526',
    '--radius': '10px',
    '--shadow': '0 20px 60px rgba(0,0,0,0.65)',
  },
  obsidian: {
    '--bg': '#0A0A0B', '--card': '#111113', '--card-hover': '#18181B',
    '--bg-input': '#0e0e10', '--border': '#27272A',
    '--text': '#FAFAFA', '--text-dim': '#71717A',
    '--accent': '#6366F1', '--accent-hover': '#818CF8',
    '--window-bg': '#111113', '--window-header': '#0A0A0B',
    '--shadow': '0 0 0 1px rgba(255,255,255,0.04), 0 20px 60px rgba(0,0,0,0.85)',
    '--radius': '8px',
  },
  void: {
    '--bg': '#09090B', '--card': '#111111', '--card-hover': '#1A1A1A',
    '--bg-input': '#0C0C0C', '--border': '#333333',
    '--text': '#EDEDED', '--text-dim': '#888888',
    '--accent': '#0070F3', '--accent-hover': '#338EF7',
    '--window-bg': '#111111', '--window-header': '#060606',
    '--shadow': '0 0 0 1px rgba(255,255,255,0.06), 0 24px 80px rgba(0,0,0,0.9)',
    '--radius': '8px',
  },
  aurora: {
    '--bg': '#0D0E17', '--card': '#13141F', '--card-hover': '#1A1C2E',
    '--bg-input': '#10111B', '--border': '#1E2035',
    '--text': '#F1F0FF', '--text-dim': '#6B7280',
    '--accent': '#8B5CF6', '--accent-hover': '#A78BFA',
    '--window-bg': '#13141F', '--window-header': '#0D0E17',
    '--shadow': '0 0 0 1px rgba(139,92,246,0.12), 0 20px 60px rgba(0,0,0,0.8)',
    '--radius': '12px',
  },
  ember: {
    '--bg': '#0C0B0A', '--card': '#141210', '--card-hover': '#1E1C19',
    '--bg-input': '#110F0D', '--border': '#2A2520',
    '--text': '#F5F0EB', '--text-dim': '#8A7F75',
    '--accent': '#FF6B35', '--accent-hover': '#FF8C5A',
    '--window-bg': '#141210', '--window-header': '#0C0B0A',
    '--shadow': '0 0 0 1px rgba(255,107,53,0.08), 0 20px 56px rgba(0,0,0,0.85)',
    '--radius': '10px',
  },
  graphite: {
    '--bg': '#0F1117', '--card': '#1A1D27', '--card-hover': '#212433',
    '--bg-input': '#141720', '--border': '#2A2F3E',
    '--text': '#FFFFFF', '--text-dim': '#A3ACB9',
    '--accent': '#635BFF', '--accent-hover': '#7A73FF',
    '--window-bg': '#1A1D27', '--window-header': '#0F1117',
    '--shadow': '0 0 0 1px rgba(255,255,255,0.04), 0 20px 60px rgba(0,0,0,0.75)',
    '--radius': '8px',
  },
  rose: {
    '--bg': '#0D0809', '--card': '#160E10', '--card-hover': '#1E1316',
    '--bg-input': '#120A0C', '--border': '#2A181C',
    '--text': '#F5E8EA', '--text-dim': '#7A555A',
    '--accent': '#FB7185', '--accent-hover': '#FDA4AF',
    '--window-bg': '#160E10', '--window-header': '#0D0809',
    '--shadow': '0 0 0 1px rgba(251,113,133,0.08), 0 20px 56px rgba(0,0,0,0.85)',
    '--radius': '12px',
  },
};

const _DARK_THEMES = new Set(['evening','night','obsidian','void','aurora','ember','graphite','rose','apple','nature','mint']);
const _NAMED_THEMES = new Set(['obsidian','void','aurora','ember','graphite','rose','apple','nature','mint']);
const FRIDAYS_THEME_MODE_KEY = 'fridays_theme_mode';
const WINDOW_THEME_MODES = ['auto', 'morning', 'afternoon', 'evening', 'night', 'obsidian', 'void', 'aurora', 'ember', 'graphite', 'rose'];

function _windowThemeIndex(mode) {
  const key = String(mode || 'auto').toLowerCase();
  const idx = WINDOW_THEME_MODES.indexOf(key);
  return idx >= 0 ? idx : 0;
}

function _windowThemeFromIndex(index) {
  const i = Math.max(0, Math.min(WINDOW_THEME_MODES.length - 1, Number(index || 0)));
  return WINDOW_THEME_MODES[i] || 'auto';
}

function _windowThemeLabel(mode) {
  const key = String(mode || 'auto').toLowerCase();
  if (key === 'auto') return 'Auto';
  if (key === 'afternoon') return 'Noon';
  return key.charAt(0).toUpperCase() + key.slice(1);
}

function resolveThemeMode(mode) {
  const requested = String(mode || 'auto').toLowerCase();
  let resolved = requested;
  if (requested === 'auto') {
    const mainSelected = String(window._selectedThemeMode || localStorage.getItem(FRIDAYS_THEME_MODE_KEY) || 'auto').toLowerCase();
    resolved = mainSelected === 'auto' ? getTimeOfDay() : mainSelected;
  }
  const isDark = _DARK_THEMES.has(resolved);
  return { resolved, isDark };
}

function applyTimeTheme(time) {
  const selectedMode = String(time || 'auto').toLowerCase();
  window._selectedThemeMode = selectedMode;
  const mode = resolveThemeMode(selectedMode);
  const colors = TIME_PERIOD_COLORS[mode.resolved] || TIME_PERIOD_COLORS.afternoon;

  // Remove all named theme classes
  _NAMED_THEMES.forEach(t => document.body.classList.remove('theme-' + t));

  // Apply CSS vars
  Object.entries(colors).forEach(([key, value]) => {
    document.documentElement.style.setProperty(key, value);
  });

  // For named themes also apply the body class (for gradient bg etc.)
  if (_NAMED_THEMES.has(mode.resolved)) {
    document.body.classList.add('theme-' + mode.resolved);
  }

  document.body.classList.toggle('mode-dark', mode.isDark);
  document.body.classList.toggle('mode-light', !mode.isDark);

  // Persist
  window._currentTheme = mode.resolved;
  try { localStorage.setItem(FRIDAYS_THEME_MODE_KEY, selectedMode); } catch(e) {}
  try { localStorage.setItem('fridays_theme', mode.resolved); } catch(e) {}

  refreshAutoWindowThemes();

  // Sync settings modal highlight
  _markThemeActive(document.querySelector(`[data-theme="${mode.resolved}"]`));
}

function _markThemeActive(btn) {
  // Clear active ring from all theme buttons in the settings modal
  document.querySelectorAll('#settings-box [data-theme]').forEach(b => {
    b.style.outline = '';
    b.style.boxShadow = b.style.boxShadow?.replace(/,?\s*0 0 0 3px[^,)]*/g, '') || '';
  });
  if (!btn) return;
  // Highlight the selected button with an inset ring
  btn.style.outline = '2px solid var(--accent)';
  btn.style.outlineOffset = '2px';
}

function applyWindowThemeToWindow(win, mode) {
  if (!win || !win.el) return;
  const resolvedMode = resolveThemeMode(mode || 'auto');
  const colors = TIME_PERIOD_COLORS[resolvedMode.resolved] || TIME_PERIOD_COLORS.afternoon;

  Object.entries(colors).forEach(([key, value]) => {
    win.el.style.setProperty(key, value);
  });

  const chips = win.el.querySelectorAll('.window-theme-chip');
  chips.forEach((chip) => {
    chip.classList.toggle('active', chip.dataset.theme === (mode || 'auto'));
  });

  const labelEl = win.el.querySelector('#win-theme-label-' + win.id);
  if (labelEl) labelEl.textContent = _windowThemeLabel(mode || 'auto');

  win.el.classList.toggle('window-dark', resolvedMode.isDark);
  win.el.classList.toggle('window-light', !resolvedMode.isDark);

  win.windowTheme = mode;
}

function refreshAutoWindowThemes() {
  if (!window.winManager || !winManager.windows) return;
  winManager.windows.forEach((win) => {
    if ((win.windowTheme || 'auto') === 'auto') {
      applyWindowThemeToWindow(win, 'auto');
    }
  });
}

function setWindowQuickTheme(id, mode) {
  const win = winManager.windows.get(id);
  if (!win) return;
  const next = WINDOW_THEME_MODES.includes(String(mode || '').toLowerCase()) ? String(mode).toLowerCase() : 'auto';
  applyWindowThemeToWindow(win, next);
  winManager.save();
  const label = _windowThemeLabel(next);
  showToast(`${win.title.replace(/^[^\w\s]+\s*/, '')}: ${label} theme`, 'info');
}

function onWindowThemeSliderChange(id, sliderValue) {
  const mode = _windowThemeFromIndex(sliderValue);
  setWindowQuickTheme(id, mode);
}

function loadSettings() {
  const defaultSettings = {
    time: 'auto',
    opacity: 5,  // 5% transparent = 95% opaque by default
    accent: '#FF9E4D',
    setAsDefault: false
  };

  const settings = JSON.parse(localStorage.getItem('fridays-settings') || JSON.stringify(defaultSettings));

  // settings.opacity stores transparency %. Guard against invisible-window settings.
  const transparency = Math.max(0, Math.min(85, Number(settings.opacity ?? 0)));
  if (transparency !== settings.opacity) {
    settings.opacity = transparency;
    localStorage.setItem('fridays-settings', JSON.stringify(settings));
  }

  // Restore saved named theme (e.g. obsidian/void) or fall back to settings.time
  const savedTheme = localStorage.getItem(FRIDAYS_THEME_MODE_KEY)
    || localStorage.getItem('fridays_theme')
    || settings.time
    || 'auto';
  applyTimeTheme(savedTheme);

  // Mark the active theme button in the settings modal
  _markThemeActive(document.querySelector(`[data-theme="${savedTheme}"]`));

  // Apply transparency (settings.opacity stores transparency %, so invert to get opacity)
  document.documentElement.style.setProperty('--glass-opacity', (100 - transparency) / 100);

  // Sync opacity slider
  const opacitySlider = document.getElementById('opacity-slider');
  if (opacitySlider) opacitySlider.value = 100 - transparency;

  // Apply accent color
  document.documentElement.style.setProperty('--accent', settings.accent);
  document.querySelector(`[data-color="${settings.accent}"]`)?.classList.add('active');

  // Update opacity display
  const opacityValue = document.getElementById('opacity-value');
  if (opacityValue) opacityValue.textContent = transparency + '%';

  _syncChatUiScaleControls(window.__fridaysChatUiScale || CHAT_UI_SCALE_DEFAULT);

  return settings;
}

function updateTimeDisplay() {
  // Legacy stub — time slider removed. No-op.
}

function updateHomeTimeDisplay() {
  const now = new Date();
  const timeStr = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true });
  
  // Get current theme mood
  const settings = JSON.parse(localStorage.getItem('fridays-settings') || '{"time":"auto"}');
  const hour = now.getHours();
  let currentTheme = settings.time;
  
  if (currentTheme === 'auto') {
    if (hour >= 6 && hour < 12) currentTheme = 'morning';
    else if (hour >= 12 && hour < 17) currentTheme = 'afternoon';
    else if (hour >= 17 && hour < 21) currentTheme = 'evening';
    else currentTheme = 'night';
  }
  
  const moodLabels = {
    'morning': '🌅 Morning Vibes',
    'afternoon': '☀️ Afternoon Energy',
    'evening': '🌆 Evening Mood',
    'night': '🌙 Night Mode'
  };
  
  const timeDisplay = document.getElementById('time-display');
  if (timeDisplay) {
    timeDisplay.innerHTML = `
      <div class="actual-time">${timeStr}</div>
      <div class="feels-like">${moodLabels[currentTheme] || 'Auto'}</div>
    `;
  }
}

function drawAnalogClock(offset) {
  const utc = new Date().getTime() + new Date().getTimezoneOffset() * 60000;
  const localTime = new Date(utc + (3600000 * offset));
  
  const hours = localTime.getHours() % 12;
  const minutes = localTime.getMinutes();
  const seconds = localTime.getSeconds();
  
  const hourAngle = (hours * 30) + (minutes * 0.5);  // 360 / 12 = 30 per hour
  const minuteAngle = (minutes * 6) + (seconds * 0.1);  // 360 / 60 = 6 per minute
  const secondAngle = seconds * 6;  // 360 / 60 = 6 per second
  
  return `
    <svg width="48" height="48" viewBox="0 0 48 48" style="background: rgba(255,255,255,0.05); border-radius: 50%; border: 1px solid var(--border);">
      <!-- Clock face -->
      <circle cx="24" cy="24" r="22" fill="none" stroke="var(--border)" stroke-width="0.5"/>
      
      <!-- Hour markers -->
      <circle cx="24" cy="4" r="1" fill="var(--text-dim)" opacity="0.3"/>
      <circle cx="44" cy="24" r="1" fill="var(--text-dim)" opacity="0.3"/>
      <circle cx="24" cy="44" r="1" fill="var(--text-dim)" opacity="0.3"/>
      <circle cx="4" cy="24" r="1" fill="var(--text-dim)" opacity="0.3"/>
      
      <!-- Hour hand -->
      <line x1="24" y1="24" x2="24" y2="12" 
        stroke="var(--text)" stroke-width="2" stroke-linecap="round"
        transform="rotate(${hourAngle} 24 24)"/>
      
      <!-- Minute hand -->
      <line x1="24" y1="24" x2="24" y2="6" 
        stroke="var(--text-dim)" stroke-width="1.5" stroke-linecap="round"
        transform="rotate(${minuteAngle} 24 24)"/>
      
      <!-- Center dot -->
      <circle cx="24" cy="24" r="1.5" fill="var(--accent)"/>
    </svg>
  `;
}

const WORLD_CLOCKS_STORAGE_KEY = 'fridays-world-clock-zones-v2';
const WORLD_CLOCK_DEFAULTS = [
  { city: 'Melbourne', timeZone: 'Australia/Melbourne' },
  { city: 'Singapore', timeZone: 'Asia/Singapore' },
  { city: 'Delhi', timeZone: 'Asia/Kolkata' },
  { city: 'Cape Town', timeZone: 'Africa/Johannesburg' },
  { city: 'New York', timeZone: 'America/New_York' }
];

function getAllTimezones() {
  return [
    { city: 'UTC', timeZone: 'UTC' },
    { city: 'Melbourne', timeZone: 'Australia/Melbourne' },
    { city: 'Sydney', timeZone: 'Australia/Sydney' },
    { city: 'Auckland', timeZone: 'Pacific/Auckland' },
    { city: 'Singapore', timeZone: 'Asia/Singapore' },
    { city: 'Delhi', timeZone: 'Asia/Kolkata' },
    { city: 'Mumbai', timeZone: 'Asia/Kolkata' },
    { city: 'Dubai', timeZone: 'Asia/Dubai' },
    { city: 'Bangkok', timeZone: 'Asia/Bangkok' },
    { city: 'Jakarta', timeZone: 'Asia/Jakarta' },
    { city: 'Manila', timeZone: 'Asia/Manila' },
    { city: 'Hong Kong', timeZone: 'Asia/Hong_Kong' },
    { city: 'Shanghai', timeZone: 'Asia/Shanghai' },
    { city: 'Seoul', timeZone: 'Asia/Seoul' },
    { city: 'Tokyo', timeZone: 'Asia/Tokyo' },
    { city: 'London', timeZone: 'Europe/London' },
    { city: 'Paris', timeZone: 'Europe/Paris' },
    { city: 'Istanbul', timeZone: 'Europe/Istanbul' },
    { city: 'Moscow', timeZone: 'Europe/Moscow' },
    { city: 'Cape Town', timeZone: 'Africa/Johannesburg' },
    { city: 'New York', timeZone: 'America/New_York' },
    { city: 'Chicago', timeZone: 'America/Chicago' },
    { city: 'Denver', timeZone: 'America/Denver' },
    { city: 'Los Angeles', timeZone: 'America/Los_Angeles' },
    { city: 'Hawaii', timeZone: 'Pacific/Honolulu' },
    { city: 'São Paulo', timeZone: 'America/Sao_Paulo' },
    { city: 'Buenos Aires', timeZone: 'America/Argentina/Buenos_Aires' },
    { city: 'Fiji', timeZone: 'Pacific/Fiji' }
  ];
}

function findTimezoneByLegacyName(name) {
  const lookup = {
    'UTC': 'UTC',
    'London': 'Europe/London',
    'Paris': 'Europe/Paris',
    'Dubai': 'Asia/Dubai',
    'Delhi': 'Asia/Kolkata',
    'Bangkok': 'Asia/Bangkok',
    'Singapore': 'Asia/Singapore',
    'Tokyo': 'Asia/Tokyo',
    'Sydney': 'Australia/Sydney',
    'Melbourne': 'Australia/Melbourne',
    'Auckland': 'Pacific/Auckland',
    'Fiji': 'Pacific/Fiji',
    'Hawaii': 'Pacific/Honolulu',
    'Los Angeles': 'America/Los_Angeles',
    'Denver': 'America/Denver',
    'Chicago': 'America/Chicago',
    'New York': 'America/New_York',
    'São Paulo': 'America/Sao_Paulo',
    'Buenos Aires': 'America/Argentina/Buenos_Aires',
    'Cape Town': 'Africa/Johannesburg',
    'Istanbul': 'Europe/Istanbul',
    'Moscow': 'Europe/Moscow',
    'Hong Kong': 'Asia/Hong_Kong',
    'Seoul': 'Asia/Seoul',
    'Shanghai': 'Asia/Shanghai',
    'Mumbai': 'Asia/Kolkata',
    'Jakarta': 'Asia/Jakarta',
    'Manila': 'Asia/Manila'
  };
  return lookup[name] || null;
}

function normalizeWorldClockZone(entry) {
  if (!entry || typeof entry !== 'object') return null;
  const allZones = getAllTimezones();
  const byTimeZone = entry.timeZone
    ? allZones.find(zone => zone.timeZone === entry.timeZone)
    : null;
  if (byTimeZone) return byTimeZone;

  const legacyTimeZone = entry.name ? findTimezoneByLegacyName(entry.name) : null;
  if (legacyTimeZone) {
    return allZones.find(zone => zone.timeZone === legacyTimeZone) || null;
  }

  if (entry.city) {
    return allZones.find(zone => zone.city === entry.city) || null;
  }

  return null;
}

function loadWorldClockZones() {
  let parsed = [];
  try {
    parsed = JSON.parse(localStorage.getItem(WORLD_CLOCKS_STORAGE_KEY) || '[]');
  } catch (e) {
    parsed = [];
  }

  if (!Array.isArray(parsed) || !parsed.length) {
    try {
      parsed = JSON.parse(localStorage.getItem('world-clock-zones') || '[]');
    } catch (e) {
      parsed = [];
    }
  }

  const normalized = parsed
    .map(normalizeWorldClockZone)
    .filter(Boolean)
    .slice(0, WORLD_CLOCK_DEFAULTS.length);

  const finalZones = normalized.length === WORLD_CLOCK_DEFAULTS.length
    ? normalized
    : WORLD_CLOCK_DEFAULTS.map((zone, idx) => normalized[idx] || zone);

  localStorage.setItem(WORLD_CLOCKS_STORAGE_KEY, JSON.stringify(finalZones));
  return finalZones;
}

function saveWorldClockZones(zones) {
  localStorage.setItem(WORLD_CLOCKS_STORAGE_KEY, JSON.stringify(zones));
  localStorage.setItem('world-clock-zones', JSON.stringify(
    zones.map(zone => ({ name: zone.city, timeZone: zone.timeZone }))
  ));
}

function getTimeForTimezone(timeZone) {
  const now = new Date();
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone,
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  }).formatToParts(now);

  const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
  const offsetLabel = new Intl.DateTimeFormat('en', {
    timeZone,
    timeZoneName: 'shortOffset'
  }).formatToParts(now).find(part => part.type === 'timeZoneName')?.value || 'UTC';

  return {
    hours: Number(values.hour || 0),
    minutes: Number(values.minute || 0),
    seconds: Number(values.second || 0),
    offsetLabel: offsetLabel.replace('GMT', 'UTC')
  };
}

// Create digital time display (HH:MM:SS)
function createDigitalTime(time) {
  const h = String(time.hours).padStart(2, '0');
  const m = String(time.minutes).padStart(2, '0');
  const s = String(time.seconds).padStart(2, '0');
  return `${h}:${m}:${s}`;
}

// Create analogue clock with CSS transforms
function createAnalogClockHTML(time) {
  const hours = time.hours % 12;
  const minutes = time.minutes;
  const seconds = time.seconds;
  
  const secondAngle = (seconds * 6);
  const minuteAngle = (minutes * 6) + (seconds * 0.1);
  const hourAngle = (hours * 30) + (minutes * 0.5);
  
  return `
    <div style="position: relative; width: 56px; height: 56px; border-radius: 50%; background: rgba(255,255,255,0.05); border: 2px solid var(--accent); display: flex; align-items: center; justify-content: center;">
      <!-- Hour hand -->
      <div style="position: absolute; width: 3px; height: 16px; background: var(--accent); border-radius: 2px; bottom: 50%; left: 50%; margin-left: -1.5px; transform-origin: bottom center; transform: translateX(-50%) rotate(${hourAngle}deg);"></div>
      
      <!-- Minute hand -->
      <div style="position: absolute; width: 2px; height: 22px; background: var(--text); border-radius: 1px; bottom: 50%; left: 50%; margin-left: -1px; transform-origin: bottom center; transform: translateX(-50%) rotate(${minuteAngle}deg);"></div>
      
      <!-- Second hand -->
      <div style="position: absolute; width: 1px; height: 26px; background: var(--accent); bottom: 50%; left: 50%; margin-left: -0.5px; transform-origin: bottom center; transform: translateX(-50%) rotate(${secondAngle}deg);"></div>
      
      <!-- Center dot -->
      <div style="width: 6px; height: 6px; background: var(--accent); border-radius: 50%; z-index: 10;"></div>
    </div>
  `;
}

function updateWorldClocks() {
  const container = document.getElementById('world-clocks');
  if (!container) {
    console.log('ERROR: world-clocks container not found');
    return;
  }
  
  try {
    const savedZones = loadWorldClockZones();
    
    let html = '';
    savedZones.forEach((zone, idx) => {
      const time = getTimeForTimezone(zone.timeZone);
      const digital = createDigitalTime(time);
      const analog = createAnalogClockHTML(time);
      
      html += `
        <div class="world-clock-item" onclick="openTimezonePicker(${idx})" style="gap: 8px;">
          ${analog}
          <div style="font-family: 'Courier New', monospace; font-size: 11px; color: var(--accent); letter-spacing: 1px; text-align: center; line-height: 1.3;">${digital}</div>
          <div class="zone" style="font-size: 11px;">${zone.city}</div>
          <div style="font-size: 10px; color: var(--text-dim);">${time.offsetLabel}</div>
        </div>
      `;
    });
    
    container.innerHTML = html;
  } catch(e) {
    console.log('ERROR in clocks:', e.message, e.stack);
  }
}

function renderTimezoneOptions(queryText) {
  const modal = document.getElementById('timezone-picker-modal');
  const list = document.getElementById('timezone-list');
  if (!modal || !list) return;

  const currentZones = loadWorldClockZones();
  const currentZone = currentZones[modal.currentClockIndex];
  const query = (queryText || '').trim().toLowerCase();
  const filtered = getAllTimezones().filter(zone => {
    if (!query) return true;
    return zone.city.toLowerCase().includes(query) || zone.timeZone.toLowerCase().includes(query);
  });

  list.innerHTML = filtered.map((zone, idx) => {
    const isCurrent = currentZone && currentZone.timeZone === zone.timeZone;
    return `
      <div class="timezone-option ${isCurrent ? 'current' : ''}" onclick="selectTimezoneOption(${idx})">
        <div>${zone.city}</div>
        <div style="font-size: 10px; color: var(--text-dim); margin-top: 2px;">${zone.timeZone}</div>
      </div>
    `;
  }).join('');

  modal.filteredTimezones = filtered;
}

function openTimezonePicker(clockIndex) {
  const modal = document.getElementById('timezone-picker-modal');
  const search = document.getElementById('timezone-search');
  if (!modal || !search) return;

  modal.classList.add('open');
  modal.currentClockIndex = clockIndex;
  search.value = '';
  renderTimezoneOptions('');
  search.oninput = (e) => {
    renderTimezoneOptions(e.target.value || '');
  };
  search.focus();
}

function selectTimezoneOption(optionIndex) {
  const modal = document.getElementById('timezone-picker-modal');
  if (!modal) return;

  const selected = (modal.filteredTimezones || [])[optionIndex];
  if (!selected) return;

  selectTimezone(selected.timeZone, selected.city);
}

function selectTimezone(timeZone, city) {
  const modal = document.getElementById('timezone-picker-modal');
  if (!modal) return;
  const clockIndex = modal.currentClockIndex;
  
  const savedZones = loadWorldClockZones();
  
  savedZones[clockIndex] = { city, timeZone };
  saveWorldClockZones(savedZones);
  
  modal.classList.remove('open');
  updateWorldClocks();
  document.getElementById('timezone-search').value = '';
}

function initClocks() {
  if (window.__fridaysClocksInitialized) {
    updateHomeTimeDisplay();
    updateWorldClocks();
    return;
  }
  window.__fridaysClocksInitialized = true;
  
  updateHomeTimeDisplay();
  updateWorldClocks();
  
  setInterval(updateHomeTimeDisplay, 60000);
  setInterval(updateWorldClocks, 1000);
  
  const modal = document.getElementById('timezone-picker-modal');
  if (modal) {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) {
        modal.classList.remove('open');
      }
    });
  }
}

function saveSettings() {
  // Current theme set by applyTimeTheme()
  const currentTheme = window._selectedThemeMode || localStorage.getItem(FRIDAYS_THEME_MODE_KEY) || 'auto';

  const settings = {
    time: currentTheme,
    opacity: 100 - parseInt(document.getElementById('opacity-slider').value || '95'),
    accent: Array.from(document.querySelectorAll('[data-color]')).find(b => b.classList.contains('active'))?.dataset.color || '#FF9E4D',
    setAsDefault: false,
  };

  localStorage.setItem('fridays-settings', JSON.stringify(settings));
  localStorage.setItem(FRIDAYS_THEME_MODE_KEY, currentTheme);
  showToast('Theme saved', 'success');

  document.documentElement.style.setProperty('--glass-opacity', (100 - settings.opacity) / 100);
  document.documentElement.style.setProperty('--accent', settings.accent);

  closeSettings();
}

function toggleSettings() {
  document.getElementById('settings-modal').classList.toggle('open');
}

function closeSettings() {
  document.getElementById('settings-modal').classList.remove('open');
}

