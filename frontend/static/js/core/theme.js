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

const FRIDAYS_THEME_MODE_KEY = 'fridays_theme_mode';
const FRIDAYS_ATMOSPHERE_VALUE_KEY = 'fridays_atmosphere_value';
const FRIDAYS_ACCENT_VALUE_KEY = 'fridays_accent_value';
const FRIDAYS_HUE_VALUE_KEY = 'fridays_hue_value';
const FRIDAYS_CONTRAST_VALUE_KEY = 'fridays_contrast_value';
const FRIDAYS_SCENE_KEY = 'fridays_scene';
const FRIDAYS_SCENE_EFFECT_KEY = 'fridays_scene_effect';
const FRIDAYS_SCENE_LAYERS_KEY = 'fridays_scene_layers';
const FRIDAYS_FOUNDATION_MODE_KEY = 'fridays_foundation_mode';
const FRIDAYS_GLOW_VALUE_KEY = 'fridays_glow_value';
const SCENE_MODES = ['off', 'beach', 'forest', 'rain'];
const FOUNDATION_MODES = ['auto', 'light', 'dark'];
const SCENE_EFFECT_MODES = ['on', 'off'];
const SCENE_LAYER_KEYS = ['orbs', 'lattice', 'clusters', 'scene'];
const SCENE_LAYER_DEFAULTS = Object.freeze({ orbs: true, lattice: true, clusters: true, scene: true });
const WINDOW_THEME_MODES = ['auto', 'morning', 'afternoon', 'evening', 'night'];
const ATMOSPHERE_PRESET_VALUES = {
  morning: 10,
  afternoon: 38,
  evening: 70,
  night: 100,
  lumen: 16,
  sky: 42,
  solar: 62,
  obsidian: 100,
  void: 100,
  aurora: 82,
  ember: 76,
  graphite: 92,
  rose: 74,
  midnight: 96,
  copper: 78,
  neon: 100,
  arctic: 6,
};
const ATMOSPHERE_KEYFRAMES = [
  {
    stop: 0,
    palette: {
      '--bg': '#FFF6F8',
      '--card': '#FFFDFE',
      '--card-hover': '#FFE9F0',
      '--hover': '#FFE4EE',
      '--bg-input': '#FFF3F7',
      '--border': '#F3D7E2',
      '--text': '#4B2E42',
      '--text-dim': '#9A7288',
      '--text-faint': '#D4B5C3',
      '--accent': '#FF7DB8',
      '--accent-hover': '#FF9FCB',
      '--window-bg': '#FFFDFE',
      '--window-header': '#FFE7F0',
      '--glow-a': '#FFD6E7',
      '--glow-b': '#FFEED7',
      '--mist': '#FFF6FB',
    },
  },
  {
    stop: 38,
    palette: {
      '--bg': '#F4FBFF',
      '--card': '#FFFFFF',
      '--card-hover': '#E7F5FF',
      '--hover': '#DEF2FF',
      '--bg-input': '#EEF9FF',
      '--border': '#B9D8EE',
      '--text': '#18384E',
      '--text-dim': '#3A5A72',
      '--text-faint': '#8FAFC5',
      '--accent': '#27CBFF',
      '--accent-hover': '#62DEFF',
      '--window-bg': '#FBFEFF',
      '--window-header': '#E5F5FF',
      '--glow-a': '#CDEEFF',
      '--glow-b': '#E6F6FF',
      '--mist': '#EDF8FF',
    },
  },
  {
    stop: 54,
    palette: {
      '--bg': '#FFF8EE',
      '--card': '#FFFDF9',
      '--card-hover': '#FFF1DC',
      '--hover': '#FFE9D0',
      '--bg-input': '#FFF6E8',
      '--border': '#E8CCAA',
      '--text': '#4A311D',
      '--text-dim': '#8E6B4F',
      '--text-faint': '#C7A382',
      '--accent': '#FFB15A',
      '--accent-hover': '#FFC680',
      '--window-bg': '#FFFDF9',
      '--window-header': '#FFF0DB',
      '--glow-a': '#FFE1B8',
      '--glow-b': '#FFF1D8',
      '--mist': '#FFF7EF',
    },
  },
  {
    stop: 70,
    palette: {
      '--bg': '#2F2336',
      '--card': '#3F2E49',
      '--card-hover': '#50385C',
      '--hover': '#5A4167',
      '--bg-input': '#382941',
      '--border': '#9278A0',
      '--text': '#FFF8FC',
      '--text-dim': '#E1D0E2',
      '--text-faint': '#9E88A5',
      '--accent': '#FF9752',
      '--accent-hover': '#FFBF8A',
      '--window-bg': '#392A42',
      '--window-header': '#261C2E',
      '--glow-a': '#E98E50',
      '--glow-b': '#5B4B86',
      '--mist': '#36283D',
    },
  },
  {
    stop: 100,
    palette: {
      '--bg': '#151A22',
      '--card': '#1F2732',
      '--card-hover': '#27313E',
      '--hover': '#2D3948',
      '--bg-input': '#1A212C',
      '--border': '#566576',
      '--text': '#F4F8FD',
      '--text-dim': '#B7C3D0',
      '--text-faint': '#74808D',
      '--accent': '#86B7F2',
      '--accent-hover': '#B8D6FA',
      '--window-bg': '#1A212C',
      '--window-header': '#10151D',
      '--glow-a': '#293646',
      '--glow-b': '#18222E',
      '--mist': '#171D26',
    },
  },
];

const ACCENT_KEYFRAMES = [
  { stop: 0, color: '#FF7DB8', hover: '#FF9FCB', label: 'Rose' },
  { stop: 25, color: '#FFB15A', hover: '#FFC680', label: 'Sunrise' },
  { stop: 50, color: '#27CBFF', hover: '#62DEFF', label: 'Cyan' },
  { stop: 75, color: '#7BD97B', hover: '#A0E9A0', label: 'Lime' },
  { stop: 100, color: '#B38CFF', hover: '#CFB3FF', label: 'Violet' },
];

const SCENE_PALETTE_STRIPS = {
  off: {
    gradient: 'linear-gradient(90deg,#ff8fbe 0%,#ffcc9f 18%,#bde9ff 42%,#ffab63 70%,#775ac0 84%,#334253 100%)',
    labels: ['Pink Dawn', 'Blue Noon', 'Amber Dusk', 'Grey Night'],
  },
  beach: {
    gradient: 'linear-gradient(90deg,#0f3c78 0%,#1b5db0 22%,#2c8fd6 46%,#ff9a3d 74%,#ffbf6f 100%)',
    labels: ['Deep Tide', 'Sea Blue', 'Sunline', 'Warm Surf'],
  },
  forest: {
    gradient: 'linear-gradient(90deg,#2b3133 0%,#43544a 22%,#5f7b45 48%,#b4a84c 76%,#e2d066 100%)',
    labels: ['Dark Bark', 'Pine Green', 'Canopy', 'Yellow Moss'],
  },
  rain: {
    gradient: 'linear-gradient(90deg,#5a6c78 0%,#6d8592 24%,#7ea3ae 48%,#7b9382 76%,#a9b8b2 100%)',
    labels: ['Rain Grey', 'Soft Blue', 'Wet Glass', 'Green Mist'],
  },
};

const ATMOSPHERE_TIME_ANCHORS = [
  { value: 0, minute: 360 },
  { value: 38, minute: 720 },
  { value: 70, minute: 1080 },
  { value: 88, minute: 1320 },
  { value: 100, minute: 1439 },
];

function _clampAtmosphereValue(value) {
  return Math.max(0, Math.min(100, Number(value ?? 0)));
}

function _clampTransparencyValue(value) {
  return Math.max(0, Math.min(30, Number(value ?? 0)));
}

function _normalizeAtmosphereMode(mode) {
  const key = String(mode || 'auto').toLowerCase();
  return key === 'auto' ? 'auto' : 'manual';
}

function _normalizeFoundationMode(mode) {
  const key = String(mode || 'auto').toLowerCase();
  return FOUNDATION_MODES.includes(key) ? key : 'auto';
}

function _normalizeSceneEffectMode(mode) {
  const key = String(mode || 'on').toLowerCase();
  return SCENE_EFFECT_MODES.includes(key) ? key : 'on';
}

function _normalizeSceneLayers(layers) {
  const next = { ...SCENE_LAYER_DEFAULTS };
  if (!layers || typeof layers !== 'object') return next;
  SCENE_LAYER_KEYS.forEach((key) => {
    const value = layers[key];
    if (typeof value === 'string') next[key] = value !== 'off' && value !== 'false';
    else if (value !== undefined && value !== null) next[key] = !!value;
  });
  return next;
}

function _rgbFromHex(hex) {
  const clean = String(hex || '').replace('#', '').trim();
  if (clean.length !== 6) return { r: 0, g: 0, b: 0 };
  return {
    r: parseInt(clean.slice(0, 2), 16),
    g: parseInt(clean.slice(2, 4), 16),
    b: parseInt(clean.slice(4, 6), 16),
  };
}

function _hexFromRgb({ r, g, b }) {
  return '#' + [r, g, b].map((value) => Math.max(0, Math.min(255, Math.round(value))).toString(16).padStart(2, '0')).join('');
}

function _rgbToHsl({ r, g, b }) {
  const rn = r / 255;
  const gn = g / 255;
  const bn = b / 255;
  const max = Math.max(rn, gn, bn);
  const min = Math.min(rn, gn, bn);
  const l = (max + min) / 2;
  const delta = max - min;

  if (delta === 0) {
    return { h: 0, s: 0, l: l * 100 };
  }

  const s = delta / (1 - Math.abs((2 * l) - 1));
  let h;
  switch (max) {
    case rn:
      h = 60 * (((gn - bn) / delta) % 6);
      break;
    case gn:
      h = 60 * (((bn - rn) / delta) + 2);
      break;
    default:
      h = 60 * (((rn - gn) / delta) + 4);
      break;
  }

  return { h: (h + 360) % 360, s: s * 100, l: l * 100 };
}

function _hslToRgb({ h, s, l }) {
  const hn = (((h % 360) + 360) % 360) / 360;
  const sn = Math.max(0, Math.min(100, s)) / 100;
  const ln = Math.max(0, Math.min(100, l)) / 100;

  if (sn === 0) {
    const gray = ln * 255;
    return { r: gray, g: gray, b: gray };
  }

  const q = ln < 0.5 ? ln * (1 + sn) : ln + sn - (ln * sn);
  const p = (2 * ln) - q;
  const toChannel = (t) => {
    let tc = t;
    if (tc < 0) tc += 1;
    if (tc > 1) tc -= 1;
    if (tc < 1 / 6) return p + ((q - p) * 6 * tc);
    if (tc < 1 / 2) return q;
    if (tc < 2 / 3) return p + ((q - p) * (2 / 3 - tc) * 6);
    return p;
  };

  return {
    r: toChannel(hn + 1 / 3) * 255,
    g: toChannel(hn) * 255,
    b: toChannel(hn - 1 / 3) * 255,
  };
}

function _tuneHex(hex, options = {}) {
  const { hueShift = 0, saturation = 0, contrast = 0, lightness = 0 } = options;
  const hsl = _rgbToHsl(_rgbFromHex(hex));
  const contrastShift = (hsl.l >= 50 ? 1 : -1) * contrast;
  return _hexFromRgb(_hslToRgb({
    h: hsl.h + hueShift,
    s: hsl.s + saturation,
    l: hsl.l + contrastShift + lightness,
  }));
}

function _mixHex(a, b, t) {
  const left = _rgbFromHex(a);
  const right = _rgbFromHex(b);
  return _hexFromRgb({
    r: left.r + ((right.r - left.r) * t),
    g: left.g + ((right.g - left.g) * t),
    b: left.b + ((right.b - left.b) * t),
  });
}

function _hexWithAlpha(hex, alpha) {
  const { r, g, b } = _rgbFromHex(hex);
  const a = Math.max(0, Math.min(1, Number(alpha || 0)));
  return `rgba(${r}, ${g}, ${b}, ${a})`;
}

function _interpolatePalette(value) {
  const v = _clampAtmosphereValue(value);
  let left = ATMOSPHERE_KEYFRAMES[0];
  let right = ATMOSPHERE_KEYFRAMES[ATMOSPHERE_KEYFRAMES.length - 1];

  for (let i = 0; i < ATMOSPHERE_KEYFRAMES.length - 1; i += 1) {
    const current = ATMOSPHERE_KEYFRAMES[i];
    const next = ATMOSPHERE_KEYFRAMES[i + 1];
    if (v >= current.stop && v <= next.stop) {
      left = current;
      right = next;
      break;
    }
  }

  const span = Math.max(1, right.stop - left.stop);
  const t = Math.max(0, Math.min(1, (v - left.stop) / span));
  const keys = new Set([...Object.keys(left.palette), ...Object.keys(right.palette)]);
  const palette = {};
  keys.forEach((key) => {
    palette[key] = _mixHex(left.palette[key] || right.palette[key], right.palette[key] || left.palette[key], t);
  });
  return palette;
}

function _interpolateAccent(value) {
  const v = _clampAtmosphereValue(value);
  let left = ACCENT_KEYFRAMES[0];
  let right = ACCENT_KEYFRAMES[ACCENT_KEYFRAMES.length - 1];
  for (let i = 0; i < ACCENT_KEYFRAMES.length - 1; i += 1) {
    const current = ACCENT_KEYFRAMES[i];
    const next = ACCENT_KEYFRAMES[i + 1];
    if (v >= current.stop && v <= next.stop) {
      left = current;
      right = next;
      break;
    }
  }
  const span = Math.max(1, right.stop - left.stop);
  const t = Math.max(0, Math.min(1, (v - left.stop) / span));
  return {
    color: _mixHex(left.color, right.color, t),
    hover: _mixHex(left.hover, right.hover, t),
    label: t < 0.5 ? left.label : right.label,
  };
}

function _currentSceneMode() {
  return _normalizeSceneMode(localStorage.getItem(FRIDAYS_SCENE_KEY) || document.body?.dataset?.scene || 'off');
}

function _currentSceneEffectMode() {
  return _normalizeSceneEffectMode(localStorage.getItem(FRIDAYS_SCENE_EFFECT_KEY) || document.body?.dataset?.sceneEffect || 'on');
}

function _currentSceneLayers() {
  try {
    return _normalizeSceneLayers(JSON.parse(localStorage.getItem(FRIDAYS_SCENE_LAYERS_KEY) || 'null'));
  } catch (_) {
    return _normalizeSceneLayers(null);
  }
}

function _applyScenePalette(palette, scene, atmosphereValue = 38) {
  const key = _normalizeSceneMode(scene);
  if (key === 'off') return { ...palette };

  const tuned = { ...palette };
  const surfaceKeys = ['--bg', '--card', '--card-hover', '--hover', '--bg-input', '--window-bg', '--window-header'];
  const textKeys = ['--text-dim', '--text-faint', '--border'];
  const v = _clampAtmosphereValue(atmosphereValue);
  const morningBoost = v < 26 ? 1 : v < 46 ? 0.65 : 0.25;

  if (key === 'beach') {
    surfaceKeys.forEach((name) => {
      tuned[name] = _tuneHex(tuned[name], { hueShift: -18, saturation: 12 + (12 * morningBoost), contrast: 6, lightness: -2 - (4 * morningBoost) });
    });
    textKeys.forEach((name) => {
      tuned[name] = _tuneHex(tuned[name], { hueShift: -14, saturation: 4 + (4 * morningBoost), contrast: 5 });
    });
    tuned['--accent'] = _tuneHex(tuned['--accent'], { hueShift: -28, saturation: 22, contrast: 7, lightness: -8 });
    tuned['--accent-hover'] = _tuneHex(tuned['--accent-hover'], { hueShift: -18, saturation: 18, contrast: 5, lightness: -4 });
    tuned['--glow-a'] = morningBoost > 0.5 ? '#1A5FB8' : '#2E76C7';
    tuned['--glow-b'] = morningBoost > 0.5 ? '#FF9B45' : '#FFB45A';
    tuned['--mist'] = morningBoost > 0.5 ? '#C5DCF0' : '#D8E9F6';
  } else if (key === 'forest') {
    surfaceKeys.forEach((name) => {
      tuned[name] = _tuneHex(tuned[name], { hueShift: 56, saturation: 10 + (10 * morningBoost), contrast: 8, lightness: -8 - (6 * morningBoost) });
    });
    textKeys.forEach((name) => {
      tuned[name] = _tuneHex(tuned[name], { hueShift: 34, saturation: 5 + (3 * morningBoost), contrast: 6 });
    });
    tuned['--accent'] = morningBoost > 0.5 ? '#B8C84A' : '#C8C158';
    tuned['--accent-hover'] = morningBoost > 0.5 ? '#D9E26A' : '#DED676';
    tuned['--glow-a'] = morningBoost > 0.5 ? '#406B50' : '#456248';
    tuned['--glow-b'] = morningBoost > 0.5 ? '#C8BE5A' : '#D6BD56';
    tuned['--mist'] = morningBoost > 0.5 ? '#59675B' : '#505C54';
  } else if (key === 'rain') {
    surfaceKeys.forEach((name) => {
      tuned[name] = _tuneHex(tuned[name], { hueShift: -22, saturation: -4 + (4 * morningBoost), contrast: 5, lightness: -6 - (4 * morningBoost) });
    });
    textKeys.forEach((name) => {
      tuned[name] = _tuneHex(tuned[name], { hueShift: -18, saturation: -2 + (2 * morningBoost), contrast: 4 });
    });
    tuned['--accent'] = morningBoost > 0.5 ? '#6D9FA5' : '#7EA8A2';
    tuned['--accent-hover'] = morningBoost > 0.5 ? '#8FB8B6' : '#9DC0BA';
    tuned['--glow-a'] = morningBoost > 0.5 ? '#688AA6' : '#7B90A5';
    tuned['--glow-b'] = morningBoost > 0.5 ? '#7FA394' : '#88A29A';
    tuned['--mist'] = morningBoost > 0.5 ? '#B9CAD3' : '#C9D6DA';
  }

  return tuned;
}

function _atmosphereTimeLabel(value) {
  const v = _clampAtmosphereValue(value);
  let left = ATMOSPHERE_TIME_ANCHORS[0];
  let right = ATMOSPHERE_TIME_ANCHORS[ATMOSPHERE_TIME_ANCHORS.length - 1];
  for (let i = 0; i < ATMOSPHERE_TIME_ANCHORS.length - 1; i += 1) {
    const current = ATMOSPHERE_TIME_ANCHORS[i];
    const next = ATMOSPHERE_TIME_ANCHORS[i + 1];
    if (v >= current.value && v <= next.value) {
      left = current;
      right = next;
      break;
    }
  }
  const span = Math.max(1, right.value - left.value);
  const t = Math.max(0, Math.min(1, (v - left.value) / span));
  const totalMinutes = Math.round(left.minute + ((right.minute - left.minute) * t));
  const hours = Math.floor(totalMinutes / 60) % 24;
  const minutes = totalMinutes % 60;
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
}

function _syncScenePaletteStrip(scene) {
  const key = _normalizeSceneMode(scene);
  const palette = SCENE_PALETTE_STRIPS[key] || SCENE_PALETTE_STRIPS.off;
  const strip = document.getElementById('atmosphere-palette-strip');
  if (strip) strip.style.background = palette.gradient;
  palette.labels.forEach((label, index) => {
    const el = document.getElementById(`atmosphere-stop-${index + 1}`);
    if (el) el.textContent = label;
  });
}

function _getAutoAtmosphereValue(date = new Date()) {
  const minutes = (date.getHours() * 60) + date.getMinutes();
  const anchors = [
    { minute: 0, value: 94 },
    { minute: 360, value: 0 },
    { minute: 720, value: 38 },
    { minute: 1080, value: 70 },
    { minute: 1320, value: 88 },
    { minute: 1440, value: 94 },
  ];

  for (let i = 0; i < anchors.length - 1; i += 1) {
    const current = anchors[i];
    const next = anchors[i + 1];
    if (minutes >= current.minute && minutes <= next.minute) {
      const span = Math.max(1, next.minute - current.minute);
      const t = (minutes - current.minute) / span;
      return current.value + ((next.value - current.value) * t);
    }
  }

  return 38;
}

function _atmosphereLabel(value) {
  const v = _clampAtmosphereValue(value);
  if (v < 10) return 'Pink Dawn';
  if (v < 26) return 'Morning Haze';
  if (v < 46) return 'Blue Noon';
  if (v < 62) return 'Clear Afternoon';
  if (v < 82) return 'Amber Dusk';
  if (v < 94) return 'Violet Evening';
  return 'Grey Night';
}

function _atmosphereSegment(value) {
  const v = _clampAtmosphereValue(value);
  if (v < 26) return 'morning';
  if (v < 56) return 'afternoon';
  if (v < 88) return 'evening';
  return 'night';
}

function _buildAtmosphereColors(value) {
  const v = _clampAtmosphereValue(value);
  const palette = _interpolatePalette(v);
  const scene = _currentSceneMode();
  const foundationMode = _currentFoundationMode();
  const resolvedFoundation = _resolveFoundationMode(foundationMode, v);
  const isDark = resolvedFoundation === 'dark';
  const hueShift = (_currentHueValue() - 50) * 0.7;
  const contrastDelta = (_currentContrastValue() - 50) * 0.24;
  const adjustedPalette = {};
  Object.entries(palette).forEach(([key, color]) => {
    if (key === '--bg' || key === '--card' || key === '--card-hover' || key === '--hover' || key === '--bg-input' || key === '--window-bg' || key === '--window-header') {
      adjustedPalette[key] = _tuneHex(color, { hueShift, saturation: 4 + (contrastDelta * 0.2), contrast: contrastDelta });
    } else if (key === '--border' || key === '--text-dim' || key === '--text-faint') {
      adjustedPalette[key] = _tuneHex(color, { hueShift, saturation: 2, contrast: contrastDelta * 0.85 });
    } else if (key === '--text') {
      adjustedPalette[key] = _tuneHex(color, { hueShift, saturation: 1, contrast: contrastDelta * 0.55 });
    } else if (key === '--glow-a' || key === '--glow-b' || key === '--mist') {
      adjustedPalette[key] = _tuneHex(color, { hueShift, saturation: 6, contrast: contrastDelta * 0.45 });
    } else {
      adjustedPalette[key] = _tuneHex(color, { hueShift, saturation: 8, contrast: contrastDelta * 0.35 });
    }
  });
  const scenePalette = _applyScenePalette(adjustedPalette, scene, v);
  Object.keys(adjustedPalette).forEach((key) => {
    adjustedPalette[key] = scenePalette[key] || adjustedPalette[key];
  });
  if (resolvedFoundation === 'dark') {
    adjustedPalette['--bg'] = '#090b10';
    adjustedPalette['--card'] = _mixHex(adjustedPalette['--card'], '#13171d', 0.9);
    adjustedPalette['--card-hover'] = _mixHex(adjustedPalette['--card-hover'], '#181d24', 0.88);
    adjustedPalette['--hover'] = _mixHex(adjustedPalette['--hover'], '#1b2129', 0.84);
    adjustedPalette['--bg-input'] = _mixHex(adjustedPalette['--bg-input'], '#11161c', 0.9);
    adjustedPalette['--window-bg'] = _mixHex(adjustedPalette['--window-bg'], '#10141a', 0.92);
    adjustedPalette['--window-header'] = _mixHex(adjustedPalette['--window-header'], '#0b0f14', 0.94);
    adjustedPalette['--border'] = _mixHex(adjustedPalette['--border'], '#39414b', 0.7);
    adjustedPalette['--text'] = '#F2F4F7';
    adjustedPalette['--text-dim'] = '#C1C9D3';
    adjustedPalette['--text-faint'] = '#7E8A96';
    adjustedPalette['--border'] = '#37414B';
    adjustedPalette['--glow-a'] = _tuneHex(adjustedPalette['--glow-a'], { saturation: 8, contrast: 12, lightness: -22 });
    adjustedPalette['--glow-b'] = _tuneHex(adjustedPalette['--glow-b'], { saturation: 8, contrast: 12, lightness: -24 });
    adjustedPalette['--mist'] = _tuneHex(adjustedPalette['--mist'], { saturation: -6, contrast: 6, lightness: -30 });
  } else {
    ['--bg', '--card', '--card-hover', '--hover', '--bg-input', '--window-bg', '--window-header'].forEach((key) => {
      adjustedPalette[key] = _tuneHex(adjustedPalette[key], { saturation: 1, contrast: 5, lightness: -6 });
    });
    adjustedPalette['--mist'] = _tuneHex(adjustedPalette['--mist'], { saturation: -10, contrast: -2, lightness: -14 });
    adjustedPalette['--glow-a'] = _tuneHex(adjustedPalette['--glow-a'], { saturation: 6, contrast: 6, lightness: -20 });
    adjustedPalette['--glow-b'] = _tuneHex(adjustedPalette['--glow-b'], { saturation: 6, contrast: 6, lightness: -18 });
  }
  const accent = adjustedPalette['--accent'] || '#27CBFF';
  const midrange = v >= 44 && v <= 68;
  const eveningBand = v > 68 && v < 92;
  return {
    ...adjustedPalette,
    '--foundation-mode': resolvedFoundation,
    '--radius': isDark ? '16px' : '18px',
    '--mist': midrange
      ? _hexWithAlpha(adjustedPalette['--mist'] || '#FFF7EF', 0.14)
      : eveningBand
        ? _hexWithAlpha(adjustedPalette['--mist'] || '#36283D', 0.08)
        : _hexWithAlpha(adjustedPalette['--mist'] || '#FFFFFF', isDark ? 0.03 : 0.22),
    '--shadow': isDark
      ? `0 22px 64px ${_hexWithAlpha('#000000', 0.34)}, 0 0 0 1px ${_hexWithAlpha('#FFFFFF', 0.06)}, 0 0 70px ${_hexWithAlpha(accent, 0.10)}`
      : midrange
        ? `0 14px 28px ${_hexWithAlpha(accent, 0.08)}, 0 0 0 1px ${_hexWithAlpha('#FFFFFF', 0.94)}`
        : `0 16px 36px ${_hexWithAlpha(accent, 0.12)}, 0 0 0 1px ${_hexWithAlpha('#FFFFFF', 0.90)}`,
  };
}

function _currentAccentValue() {
  return _clampAtmosphereValue(localStorage.getItem(FRIDAYS_ACCENT_VALUE_KEY) ?? 50);
}

function _currentHueValue() {
  return _clampAtmosphereValue(localStorage.getItem(FRIDAYS_HUE_VALUE_KEY) ?? 50);
}

function _currentContrastValue() {
  return _clampAtmosphereValue(localStorage.getItem(FRIDAYS_CONTRAST_VALUE_KEY) ?? 58);
}

function _currentGlowValue() {
  return _clampAtmosphereValue(localStorage.getItem(FRIDAYS_GLOW_VALUE_KEY) ?? 52);
}

function onAccentSliderInput(value) {
  const numeric = _clampAtmosphereValue(value);
  try { localStorage.setItem(FRIDAYS_ACCENT_VALUE_KEY, String(Math.round(numeric))); } catch (e) {}
  const currentMode = _normalizeAtmosphereMode(window._selectedThemeMode || localStorage.getItem(FRIDAYS_THEME_MODE_KEY) || 'auto');
  const currentAtmosphereValue = _clampAtmosphereValue(localStorage.getItem(FRIDAYS_ATMOSPHERE_VALUE_KEY) ?? window._currentAtmosphereValue ?? 38);
  applyTimeTheme(currentMode, currentMode === 'manual' ? currentAtmosphereValue : null);
}

function onHueSliderInput(value) {
  const numeric = _clampAtmosphereValue(value);
  try { localStorage.setItem(FRIDAYS_HUE_VALUE_KEY, String(Math.round(numeric))); } catch (e) {}
  const currentMode = _normalizeAtmosphereMode(window._selectedThemeMode || localStorage.getItem(FRIDAYS_THEME_MODE_KEY) || 'auto');
  const currentAtmosphereValue = _clampAtmosphereValue(localStorage.getItem(FRIDAYS_ATMOSPHERE_VALUE_KEY) ?? window._currentAtmosphereValue ?? 38);
  applyTimeTheme(currentMode, currentMode === 'manual' ? currentAtmosphereValue : null);
}

function onContrastSliderInput(value) {
  const numeric = _clampAtmosphereValue(value);
  try { localStorage.setItem(FRIDAYS_CONTRAST_VALUE_KEY, String(Math.round(numeric))); } catch (e) {}
  const currentMode = _normalizeAtmosphereMode(window._selectedThemeMode || localStorage.getItem(FRIDAYS_THEME_MODE_KEY) || 'auto');
  const currentAtmosphereValue = _clampAtmosphereValue(localStorage.getItem(FRIDAYS_ATMOSPHERE_VALUE_KEY) ?? window._currentAtmosphereValue ?? 38);
  applyTimeTheme(currentMode, currentMode === 'manual' ? currentAtmosphereValue : null);
}

function onGlowSliderInput(value) {
  const numeric = _clampAtmosphereValue(value);
  try { localStorage.setItem(FRIDAYS_GLOW_VALUE_KEY, String(Math.round(numeric))); } catch (e) {}
  const currentMode = _normalizeAtmosphereMode(window._selectedThemeMode || localStorage.getItem(FRIDAYS_THEME_MODE_KEY) || 'auto');
  const currentAtmosphereValue = _clampAtmosphereValue(localStorage.getItem(FRIDAYS_ATMOSPHERE_VALUE_KEY) ?? window._currentAtmosphereValue ?? 38);
  applyTimeTheme(currentMode, currentMode === 'manual' ? currentAtmosphereValue : null);
}

function _syncAccentControls(value) {
  const slider = document.getElementById('accent-slider');
  const label = document.getElementById('accent-value');
  const detail = document.getElementById('accent-detail');
  const numeric = Math.round(_clampAtmosphereValue(value));
  const accent = _interpolateAccent(numeric);
  if (slider) slider.value = String(numeric);
  if (label) label.textContent = `${numeric}%`;
  if (detail) detail.textContent = `${accent.label} accent`;
}

function _syncHueControls(value) {
  const slider = document.getElementById('hue-slider');
  const label = document.getElementById('hue-value');
  const detail = document.getElementById('hue-detail');
  const numeric = Math.round(_clampAtmosphereValue(value));
  const shift = numeric - 50;
  if (slider) slider.value = String(numeric);
  if (label) label.textContent = `${numeric}%`;
  if (detail) {
    detail.textContent = shift === 0 ? 'Balanced hue' : shift < 0 ? 'Warmer hue' : 'Cooler hue';
  }
}

function _syncContrastControls(value) {
  const slider = document.getElementById('contrast-slider');
  const label = document.getElementById('contrast-value');
  const detail = document.getElementById('contrast-detail');
  const numeric = Math.round(_clampAtmosphereValue(value));
  if (slider) slider.value = String(numeric);
  if (label) label.textContent = `${numeric}%`;
  if (detail) {
    detail.textContent = numeric < 42 ? 'Soft contrast' : numeric < 66 ? 'Balanced contrast' : 'Crisp contrast';
  }
}

function _syncGlowControls(value) {
  const slider = document.getElementById('glow-slider');
  const label = document.getElementById('glow-value');
  const detail = document.getElementById('glow-detail');
  const numeric = Math.round(_clampAtmosphereValue(value));
  if (slider) slider.value = String(numeric);
  if (label) label.textContent = `${numeric}%`;
  if (detail) {
    detail.textContent = numeric < 30 ? 'Quiet glow' : numeric < 65 ? 'Moody glow' : 'Animated glow';
  }
}

function _resolveFoundationMode(mode, atmosphereValue) {
  const normalized = _normalizeFoundationMode(mode);
  if (normalized === 'light') return 'light';
  if (normalized === 'dark') return 'dark';
  return Number(atmosphereValue || 0) >= 72 ? 'dark' : 'light';
}

function _currentFoundationMode() {
  return _normalizeFoundationMode(localStorage.getItem(FRIDAYS_FOUNDATION_MODE_KEY) || 'auto');
}

function _syncFoundationControls(mode, resolvedMode) {
  const modeLabel = document.getElementById('foundation-mode-label');
  if (modeLabel) {
    modeLabel.textContent = mode === 'auto'
      ? `Following Atmosphere · ${resolvedMode}`
      : `${resolvedMode.charAt(0).toUpperCase()}${resolvedMode.slice(1)} shell`;
  }
  FOUNDATION_MODES.forEach((value) => {
    const btn = document.getElementById(`foundation-${value}-btn`);
    if (!btn) return;
    const active = value === mode;
    btn.classList.toggle('active', active);
    btn.style.borderColor = active ? 'var(--accent)' : 'var(--border)';
    btn.style.color = active ? 'var(--accent)' : 'var(--text-dim)';
    btn.style.background = active ? 'color-mix(in srgb, var(--card-hover) 78%, white 22%)' : 'var(--card)';
    btn.style.boxShadow = active ? '0 0 0 1px color-mix(in srgb, var(--accent) 35%, transparent 65%)' : 'none';
  });
}

function setFoundationMode(mode) {
  const nextMode = _normalizeFoundationMode(mode);
  try { localStorage.setItem(FRIDAYS_FOUNDATION_MODE_KEY, nextMode); } catch (e) {}
  const currentAtmosphereMode = _normalizeAtmosphereMode(window._selectedThemeMode || localStorage.getItem(FRIDAYS_THEME_MODE_KEY) || 'auto');
  const currentAtmosphereValue = _clampAtmosphereValue(localStorage.getItem(FRIDAYS_ATMOSPHERE_VALUE_KEY) ?? window._currentAtmosphereValue ?? 38);
  applyTimeTheme(currentAtmosphereMode, currentAtmosphereMode === 'manual' ? currentAtmosphereValue : null);
}

function _normalizeSceneMode(scene) {
  const key = String(scene || 'beach').toLowerCase();
  return SCENE_MODES.includes(key) ? key : 'beach';
}

function _sceneLabel(scene) {
  const key = _normalizeSceneMode(scene);
  if (key === 'off') return 'Still background';
  if (key === 'beach') return 'Beach glow';
  if (key === 'forest') return 'Forest canopy';
  if (key === 'rain') return 'Rain drift';
  return 'Background scene';
}

function _sceneOpacity(scene) {
  const key = _normalizeSceneMode(scene);
  if (key === 'off') return '0.72';
  if (key === 'rain') return '0.92';
  if (key === 'forest') return '0.82';
  return '0.88';
}

function _syncSceneControls(scene) {
  const key = _normalizeSceneMode(scene);
  const detail = document.getElementById('scene-detail');
  if (detail) detail.textContent = `${_sceneLabel(key)} behind the Atmosphere`;
  _syncScenePaletteStrip(key);
  SCENE_MODES.forEach((mode) => {
    const btn = document.getElementById(`scene-${mode}-btn`);
    if (!btn) return;
    const active = mode === key;
    btn.classList.toggle('active', active);
    btn.style.borderColor = active ? 'var(--accent)' : 'var(--border)';
    btn.style.color = active ? 'var(--accent)' : 'var(--text-dim)';
    btn.style.background = active ? 'color-mix(in srgb, var(--card-hover) 78%, white 22%)' : 'var(--card)';
    btn.style.boxShadow = active ? '0 0 0 1px color-mix(in srgb, var(--accent) 35%, transparent 65%)' : 'none';
  });
}

function _syncSceneEffectControls(mode) {
  const toggle = document.getElementById('scene-effect-toggle-input');
  const label = document.getElementById('scene-effect-toggle-label');
  const isOn = mode === 'on';
  if (toggle) toggle.checked = isOn;
  if (label) label.textContent = isOn ? 'Effect On' : 'Effect Off';
}

function _syncSceneLayerControls(layers) {
  const next = _normalizeSceneLayers(layers);
  SCENE_LAYER_KEYS.forEach((key) => {
    const input = document.getElementById(`scene-layer-${key}-input`);
    if (input) input.checked = !!next[key];
  });
}

function _storeSceneLayers(layers) {
  const next = _normalizeSceneLayers(layers);
  try { localStorage.setItem(FRIDAYS_SCENE_LAYERS_KEY, JSON.stringify(next)); } catch (e) {}
  try {
    const settings = JSON.parse(localStorage.getItem('fridays-settings') || '{}');
    settings.sceneLayers = next;
    localStorage.setItem('fridays-settings', JSON.stringify(settings));
  } catch (e) {}
  return next;
}

function applyScene(scene) {
  const key = _normalizeSceneMode(scene);
  document.body.dataset.scene = key;
  const effectMode = _currentSceneEffectMode();
  const layers = _currentSceneLayers();
  document.body.dataset.sceneEffect = effectMode;
  document.body.dataset.sceneOrbs = effectMode === 'off' || !layers.orbs ? 'off' : 'on';
  document.body.dataset.sceneLattice = effectMode === 'off' || !layers.lattice ? 'off' : 'on';
  document.body.dataset.sceneClusters = effectMode === 'off' || !layers.clusters ? 'off' : 'on';
  document.body.dataset.sceneAmbient = effectMode === 'off' || !layers.scene ? 'off' : 'on';
  document.documentElement.style.setProperty('--scene-opacity', effectMode === 'off' || !layers.scene ? '0' : _sceneOpacity(key));
  try { localStorage.setItem(FRIDAYS_SCENE_KEY, key); } catch (e) {}
  _syncSceneControls(key);
  _syncSceneEffectControls(effectMode);
  _syncSceneLayerControls(layers);
  return key;
}

function setSceneMode(scene) {
  const key = applyScene(scene);
  try {
    const settings = JSON.parse(localStorage.getItem('fridays-settings') || '{}');
    settings.scene = key;
    localStorage.setItem('fridays-settings', JSON.stringify(settings));
  } catch (e) {}
  const currentMode = _normalizeAtmosphereMode(window._selectedThemeMode || localStorage.getItem(FRIDAYS_THEME_MODE_KEY) || 'auto');
  const currentAtmosphereValue = _clampAtmosphereValue(localStorage.getItem(FRIDAYS_ATMOSPHERE_VALUE_KEY) ?? window._currentAtmosphereValue ?? 38);
  applyTimeTheme(currentMode, currentMode === 'manual' ? currentAtmosphereValue : null);
}

function setSceneEffectMode(mode) {
  const next = _normalizeSceneEffectMode(mode);
  try { localStorage.setItem(FRIDAYS_SCENE_EFFECT_KEY, next); } catch (e) {}
  const currentScene = _currentSceneMode();
  applyScene(currentScene);
}

function setSceneLayerEnabled(layerKey, enabled) {
  if (!SCENE_LAYER_KEYS.includes(String(layerKey || ''))) return;
  const layers = _currentSceneLayers();
  layers[layerKey] = !!enabled;
  _storeSceneLayers(layers);
  applyScene(_currentSceneMode());
}

function _resolveAtmosphere(mode, explicitValue = null) {
  const normalizedMode = _normalizeAtmosphereMode(mode);
  let value;
  if (normalizedMode === 'auto') {
    value = _getAutoAtmosphereValue();
  } else if (explicitValue !== null && explicitValue !== undefined) {
    value = explicitValue;
  } else {
    value = localStorage.getItem(FRIDAYS_ATMOSPHERE_VALUE_KEY);
  }

  if ((value === null || value === undefined || value === '') && mode in ATMOSPHERE_PRESET_VALUES) {
    value = ATMOSPHERE_PRESET_VALUES[mode];
  }

  const finalValue = _clampAtmosphereValue(value ?? 38);
  return {
    selectedMode: normalizedMode,
    value: finalValue,
    isDark: finalValue >= 72,
    label: _atmosphereLabel(finalValue),
    segment: _atmosphereSegment(finalValue),
  };
}

function _syncAtmosphereControls(mode, value) {
  const slider = document.getElementById('atmosphere-slider');
  const valueLabel = document.getElementById('atmosphere-value');
  const detail = document.getElementById('atmosphere-detail');
  const modeLabel = document.getElementById('atmosphere-mode-label');
  const readout = document.getElementById('atmosphere-readout');
  const autoBtn = document.getElementById('atmosphere-auto-btn');
  const manualBtn = document.getElementById('atmosphere-manual-btn');
  const numeric = Math.round(_clampAtmosphereValue(value));

  if (slider) slider.value = String(numeric);
  if (valueLabel) valueLabel.textContent = _atmosphereTimeLabel(numeric);
  if (detail) detail.textContent = `${_atmosphereLabel(numeric)} · atmosphere clock`;
  if (modeLabel) modeLabel.textContent = mode === 'auto' ? 'Following time of day' : 'Manual override';
  if (readout) readout.textContent = mode === 'auto' ? `${_atmosphereLabel(numeric)} · auto` : `${_atmosphereLabel(numeric)} · manual`;
  if (autoBtn) {
    const active = mode === 'auto';
    autoBtn.classList.toggle('active', active);
    autoBtn.style.borderColor = active ? 'var(--accent)' : 'var(--border)';
    autoBtn.style.color = active ? 'var(--accent)' : 'var(--text)';
    autoBtn.style.boxShadow = active ? '0 0 0 1px color-mix(in srgb, var(--accent) 35%, transparent 65%)' : 'none';
  }
  if (manualBtn) {
    const active = mode !== 'auto';
    manualBtn.classList.toggle('active', active);
    manualBtn.style.borderColor = active ? 'var(--accent)' : 'var(--border)';
    manualBtn.style.color = active ? 'var(--accent)' : 'var(--text-dim)';
    manualBtn.style.boxShadow = active ? '0 0 0 1px color-mix(in srgb, var(--accent) 35%, transparent 65%)' : 'none';
  }
}

function setAtmosphereMode(mode) {
  const nextMode = _normalizeAtmosphereMode(mode);
  window._selectedThemeMode = nextMode;
  try { localStorage.setItem(FRIDAYS_THEME_MODE_KEY, nextMode); } catch (e) {}
  applyTimeTheme(nextMode);
}

function onAtmosphereSliderInput(value) {
  const numeric = _clampAtmosphereValue(value);
  window._selectedThemeMode = 'manual';
  try { localStorage.setItem(FRIDAYS_THEME_MODE_KEY, 'manual'); } catch (e) {}
  try { localStorage.setItem(FRIDAYS_ATMOSPHERE_VALUE_KEY, String(Math.round(numeric))); } catch (e) {}
  applyTimeTheme('manual', numeric);
}

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
  if (key === 'auto') return 'Default';
  if (key === 'afternoon') return 'Noon';
  if (key === 'evening') return 'Dusk';
  return key.charAt(0).toUpperCase() + key.slice(1);
}

function resolveThemeMode(mode, explicitValue = null) {
  return _resolveAtmosphere(mode, explicitValue);
}

function resolveWindowThemeMode(mode, explicitValue = null) {
  const key = String(mode || 'auto').toLowerCase();
  if (key !== 'auto') {
    return _resolveAtmosphere(mode, explicitValue);
  }
  const globalMode = _normalizeAtmosphereMode(window._selectedThemeMode || localStorage.getItem(FRIDAYS_THEME_MODE_KEY) || 'auto');
  const globalValue = globalMode === 'manual'
    ? _clampAtmosphereValue(localStorage.getItem(FRIDAYS_ATMOSPHERE_VALUE_KEY) ?? window._currentAtmosphereValue ?? 38)
    : null;
  return _resolveAtmosphere(globalMode, globalValue);
}

function applyTimeTheme(time, explicitValue = null) {
  const mode = resolveThemeMode(time, explicitValue);
  const colors = _buildAtmosphereColors(mode.value);
  const accentValue = _currentAccentValue();
  const hueValue = _currentHueValue();
  const contrastValue = _currentContrastValue();
  const glowValue = _currentGlowValue();
  const foundationMode = _currentFoundationMode();
  const resolvedFoundation = colors['--foundation-mode'] || _resolveFoundationMode(foundationMode, mode.value);
  const accentBase = _interpolateAccent(accentValue);
  const hueShift = (hueValue - 50) * 0.5;
  const contrastDelta = (contrastValue - 50) * 0.18;
  const accent = {
    color: _tuneHex(accentBase.color, { hueShift, saturation: 10, contrast: contrastDelta }),
    hover: _tuneHex(accentBase.hover, { hueShift, saturation: 8, contrast: contrastDelta * 0.8, lightness: 2 }),
  };

  window._selectedThemeMode = mode.selectedMode;
  window._currentTheme = mode.label;
  window._currentAtmosphereValue = mode.value;

  colors['--accent'] = accent.color;
  colors['--accent-hover'] = accent.hover;
  // Compute readable text colour for content placed ON the accent background
  const _ar = _rgbFromHex(accent.color);
  const _rl = (_ar.r / 255) ** 2.2, _gl = (_ar.g / 255) ** 2.2, _bl = (_ar.b / 255) ** 2.2;
  colors['--text-on-accent'] = (0.2126 * _rl + 0.7152 * _gl + 0.0722 * _bl) > 0.30 ? '#000' : '#fff';
  colors['--edge-glow'] = `0 0 ${4 + (glowValue * 0.16)}px ${_hexWithAlpha(accent.color, mode.isDark ? 0.08 + (glowValue * 0.0012) : 0.05 + (glowValue * 0.001))}`;
  colors['--edge-glow-hover'] = `0 0 ${10 + (glowValue * 0.24)}px ${_hexWithAlpha(accent.color, mode.isDark ? 0.14 + (glowValue * 0.0016) : 0.10 + (glowValue * 0.0012))}`;
  colors['--glow-animation'] = glowValue >= 62 ? 'edge-glow-pulse 9s ease-in-out infinite' : 'none';
  colors['--glow-hover-animation'] = glowValue >= 42 ? 'edge-glow-wave 3.6s ease-in-out infinite' : 'none';
  colors['--shadow'] = mode.isDark
    ? `0 22px 64px ${_hexWithAlpha('#000000', 0.34)}, 0 0 0 1px ${_hexWithAlpha('#FFFFFF', 0.06)}, 0 0 70px ${_hexWithAlpha(accent.color, 0.12)}`
    : `0 18px 48px ${_hexWithAlpha(accent.color, mode.value >= 44 && mode.value <= 68 ? 0.12 : 0.18)}, 0 0 0 1px ${_hexWithAlpha('#FFFFFF', 0.86)}`;

  // When foundation forces light mode over a dark atmosphere palette, the dark --bg/glow vars
  // bleed purple through the white overlay gradients. Override to clean light values.
  if (resolvedFoundation === 'light' && mode.value >= 58) {
    colors['--bg'] = '#F6F8FB';
    colors['--card'] = '#FFFFFF';
    colors['--card-hover'] = '#EDF2F8';
    colors['--hover'] = '#E4EBF5';
    colors['--bg-input'] = '#F0F4FA';
    colors['--border'] = '#C8D5E2';
    colors['--window-bg'] = '#FFFFFF';
    colors['--window-header'] = '#EDF2F8';
    colors['--text'] = '#1B2A3A';
    colors['--text-dim'] = '#526070';
    colors['--text-faint'] = '#8A9BAA';
    colors['--glow-a'] = _tuneHex(accent.color, { lightness: 34, saturation: -14 });
    colors['--glow-b'] = _tuneHex(accent.color, { lightness: 40, saturation: -22 });
    colors['--mist'] = 'rgba(255,255,255,0.38)';
  }

  Object.entries(colors).forEach(([key, value]) => {
    document.documentElement.style.setProperty(key, value);
  });

  document.body.classList.remove('theme-obsidian', 'theme-void', 'theme-aurora', 'theme-ember', 'theme-graphite', 'theme-rose', 'theme-lumen', 'theme-sky', 'theme-solar', 'theme-midnight', 'theme-copper', 'theme-neon', 'theme-arctic');
  document.body.classList.toggle('mode-dark', resolvedFoundation === 'dark');
  document.body.classList.toggle('mode-light', resolvedFoundation !== 'dark');
  document.body.dataset.atmosphereSegment = mode.segment;
  document.body.dataset.foundation = resolvedFoundation;
  document.body.style.setProperty('--atmosphere-value', String(Math.round(mode.value)));

  try { localStorage.setItem(FRIDAYS_THEME_MODE_KEY, mode.selectedMode); } catch (e) {}
  try { localStorage.setItem(FRIDAYS_ATMOSPHERE_VALUE_KEY, String(Math.round(mode.value))); } catch (e) {}
  try { localStorage.setItem('fridays_theme', mode.label); } catch (e) {}

  _syncAtmosphereControls(mode.selectedMode, mode.value);
  _syncFoundationControls(foundationMode, resolvedFoundation);
  _syncAccentControls(accentValue);
  _syncHueControls(hueValue);
  _syncContrastControls(contrastValue);
  _syncGlowControls(glowValue);
  refreshAutoWindowThemes();
}

function applyWindowThemeToWindow(win, mode) {
  if (!win || !win.el) return;
  const resolvedMode = resolveWindowThemeMode(mode || 'auto');
  const colors = _buildAtmosphereColors(resolvedMode.value);
  const foundationIsDark = colors['--foundation-mode'] === 'dark';

  Object.entries(colors).forEach(([key, value]) => {
    win.el.style.setProperty(key, value);
  });

  const chips = win.el.querySelectorAll('.window-theme-chip');
  chips.forEach((chip) => {
    chip.classList.toggle('active', chip.dataset.theme === (mode || 'auto'));
  });

  const labelEl = win.el.querySelector('#win-theme-label-' + win.id);
  if (labelEl) labelEl.textContent = mode === 'auto' ? 'Default' : resolvedMode.label;

  win.el.classList.toggle('window-dark', foundationIsDark);
  win.el.classList.toggle('window-light', !foundationIsDark);

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
  showToast(`${String(win.title || '').replace(/^[^\w\s]+\s*/, '')}: ${label} atmosphere`, 'info');
}

function onWindowThemeSliderChange(id, sliderValue) {
  const mode = _windowThemeFromIndex(sliderValue);
  setWindowQuickTheme(id, mode);
}

function loadSettings() {
  const defaultSettings = {
    time: 'auto',
    atmosphereMode: 'auto',
    foundationMode: 'auto',
    atmosphereValue: 38,
    accentValue: 50,
    hueValue: 50,
    contrastValue: 58,
    glowValue: 52,
    scene: 'beach',
    sceneEffect: 'on',
    sceneLayers: { ...SCENE_LAYER_DEFAULTS },
    opacity: 5,  // 5% transparent = 95% opaque by default
    setAsDefault: false
  };

  const settings = JSON.parse(localStorage.getItem('fridays-settings') || JSON.stringify(defaultSettings));

  // settings.opacity stores transparency %. Guard against invisible-window settings.
  const transparency = _clampTransparencyValue(settings.opacity ?? 5);
  if (transparency !== settings.opacity) {
    settings.opacity = transparency;
    localStorage.setItem('fridays-settings', JSON.stringify(settings));
  }

  const savedMode = _normalizeAtmosphereMode(
    localStorage.getItem(FRIDAYS_THEME_MODE_KEY)
    || settings.atmosphereMode
    || settings.time
    || 'auto'
  );
  const savedValue = _clampAtmosphereValue(
    localStorage.getItem(FRIDAYS_ATMOSPHERE_VALUE_KEY)
    ?? settings.atmosphereValue
    ?? 38
  );
  const accentValue = _clampAtmosphereValue(
    localStorage.getItem(FRIDAYS_ACCENT_VALUE_KEY)
    ?? settings.accentValue
    ?? 50
  );
  const hueValue = _clampAtmosphereValue(
    localStorage.getItem(FRIDAYS_HUE_VALUE_KEY)
    ?? settings.hueValue
    ?? 50
  );
  const contrastValue = _clampAtmosphereValue(
    localStorage.getItem(FRIDAYS_CONTRAST_VALUE_KEY)
    ?? settings.contrastValue
    ?? 58
  );
  const scene = _normalizeSceneMode(
    localStorage.getItem(FRIDAYS_SCENE_KEY)
    ?? settings.scene
    ?? 'beach'
  );
  const sceneEffect = _normalizeSceneEffectMode(
    localStorage.getItem(FRIDAYS_SCENE_EFFECT_KEY)
    ?? settings.sceneEffect
    ?? 'on'
  );
  const sceneLayers = _normalizeSceneLayers(
    (() => {
      try {
        return JSON.parse(localStorage.getItem(FRIDAYS_SCENE_LAYERS_KEY) || 'null') ?? settings.sceneLayers;
      } catch (_) {
        return settings.sceneLayers;
      }
    })()
  );
  const glowValue = _clampAtmosphereValue(
    localStorage.getItem(FRIDAYS_GLOW_VALUE_KEY)
    ?? settings.glowValue
    ?? 52
  );
  const foundationMode = _normalizeFoundationMode(
    localStorage.getItem(FRIDAYS_FOUNDATION_MODE_KEY)
    ?? settings.foundationMode
    ?? 'auto'
  );
  try { localStorage.setItem(FRIDAYS_ACCENT_VALUE_KEY, String(Math.round(accentValue))); } catch (e) {}
  try { localStorage.setItem(FRIDAYS_HUE_VALUE_KEY, String(Math.round(hueValue))); } catch (e) {}
  try { localStorage.setItem(FRIDAYS_CONTRAST_VALUE_KEY, String(Math.round(contrastValue))); } catch (e) {}
  try { localStorage.setItem(FRIDAYS_SCENE_KEY, scene); } catch (e) {}
  try { localStorage.setItem(FRIDAYS_SCENE_EFFECT_KEY, sceneEffect); } catch (e) {}
  try { localStorage.setItem(FRIDAYS_SCENE_LAYERS_KEY, JSON.stringify(sceneLayers)); } catch (e) {}
  try { localStorage.setItem(FRIDAYS_FOUNDATION_MODE_KEY, foundationMode); } catch (e) {}
  try { localStorage.setItem(FRIDAYS_GLOW_VALUE_KEY, String(Math.round(glowValue))); } catch (e) {}
  applyTimeTheme(savedMode, savedMode === 'manual' ? savedValue : null);
  applyScene(scene);

  // Apply transparency (settings.opacity stores transparency %, so invert to get opacity)
  document.documentElement.style.setProperty('--glass-opacity', (100 - transparency) / 100);

  // Sync opacity slider
  const opacitySlider = document.getElementById('opacity-slider');
  if (opacitySlider) opacitySlider.value = transparency;

  // Update opacity display
  const opacityValue = document.getElementById('opacity-value');
  if (opacityValue) opacityValue.textContent = transparency + '%';

  _syncChatUiScaleControls(window.__fridaysChatUiScale || CHAT_UI_SCALE_DEFAULT);
  _syncAccentControls(accentValue);
  _syncHueControls(hueValue);
  _syncContrastControls(contrastValue);
  _syncGlowControls(glowValue);
  _syncSceneControls(scene);
  _syncSceneEffectControls(sceneEffect);
  _syncSceneLayerControls(sceneLayers);

  return settings;
}

function updateTimeDisplay() {
  // Legacy stub — time slider removed. No-op.
}

function updateHomeTimeDisplay() {
  const now = new Date();
  const timeStr = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true });
  const mode = _normalizeAtmosphereMode(window._selectedThemeMode || localStorage.getItem(FRIDAYS_THEME_MODE_KEY) || 'auto');
  const value = mode === 'auto'
    ? _getAutoAtmosphereValue(now)
    : _clampAtmosphereValue(localStorage.getItem(FRIDAYS_ATMOSPHERE_VALUE_KEY) ?? window._currentAtmosphereValue ?? 38);
  const moodLabel = _atmosphereLabel(value);
  
  const timeDisplay = document.getElementById('time-display');
  if (timeDisplay) {
    timeDisplay.innerHTML = `
      <div class="actual-time">${timeStr}</div>
      <div class="feels-like">Atmosphere · ${moodLabel}</div>
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

// Weather cache for world clocks
let _clockWeatherCache = {};   // {city: {data, fetchedAt}}
const _WEATHER_CACHE_TTL = 900000; // 15 minutes

// WMO weather code → inline SVG icon mapping
function _weatherIcon(code, isDay) {
  const c = Number(code);
  const sun = '<svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px"><circle cx="8" cy="8" r="3" stroke="currentColor" stroke-width="1.3"/><path d="M8 2.5v2M8 11.5v2M2.5 8h2M11.5 8h2M4.1 4.1l1.4 1.4M10.5 10.5l1.4 1.4M4.1 11.9l1.4-1.4M10.5 5.5l1.4-1.4" stroke="currentColor" stroke-width="1" stroke-linecap="round"/></svg>';
  const moon = '<svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px"><path d="M10 3a5 5 0 1 0 3 7 4 4 0 0 1-3-7z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>';
  const cloud = '<svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px"><path d="M4.5 11.5a3 3 0 0 1-.4-6A4 4 0 0 1 12 7a2.5 2.5 0 0 1 .5 5h-8z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>';
  const rain = '<svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px"><path d="M4.5 9a3 3 0 0 1-.4-6A4 4 0 0 1 12 5a2.5 2.5 0 0 1 .5 4h-8z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M6 11v2M8 11.5v2M10 11v2" stroke="currentColor" stroke-width="1" stroke-linecap="round"/></svg>';
  const snow = '<svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px"><path d="M4.5 9a3 3 0 0 1-.4-6A4 4 0 0 1 12 5a2.5 2.5 0 0 1 .5 4h-8z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><circle cx="6" cy="11.5" r=".7" fill="currentColor"/><circle cx="8.5" cy="12.5" r=".7" fill="currentColor"/><circle cx="10.5" cy="11" r=".7" fill="currentColor"/></svg>';
  const storm = '<svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px"><path d="M4.5 8.5a3 3 0 0 1-.4-6A4 4 0 0 1 12 4.5a2.5 2.5 0 0 1 .5 4h-8z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M9 9l-2 3h2.5l-1.5 3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const fog = '<svg viewBox="0 0 16 16" width="11" height="11" fill="none" style="vertical-align:-1px"><path d="M3 7h10M3 9.5h10M3 12h10" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>';

  if (c === 0) return isDay ? sun : moon;                         // clear sky
  if (c === 1) return isDay ? sun : moon;                         // mainly clear
  if (c <= 3) return cloud;                                        // partly cloudy / overcast
  if (c >= 45 && c <= 48) return fog;                              // fog / rime fog
  if (c >= 51 && c <= 57) return rain;                             // drizzle
  if (c >= 61 && c <= 67) return rain;                             // rain
  if (c >= 71 && c <= 77) return snow;                             // snow
  if (c >= 80 && c <= 82) return rain;                             // rain showers
  if (c >= 85 && c <= 86) return snow;                             // snow showers
  if (c >= 95 && c <= 99) return storm;                            // thunderstorm
  return cloud;                                                    // fallback
}

function _fetchClockWeather() {
  const zones = loadWorldClockZones();
  const cities = zones.map(z => z.city).join(',');
  if (!cities) return;
  fetch('/api/weather?cities=' + encodeURIComponent(cities))
    .then(r => r.json())
    .then(data => {
      const now = Date.now();
      for (const [city, w] of Object.entries(data || {})) {
        _clockWeatherCache[city] = { data: w, fetchedAt: now };
      }
    })
    .catch(() => {});
}

function _getClockWeather(city) {
  const entry = _clockWeatherCache[city];
  if (!entry) return null;
  if (Date.now() - entry.fetchedAt > _WEATHER_CACHE_TTL * 2) return null;
  return entry.data;
}

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
      const weather = _getClockWeather(zone.city);
      const weatherHtml = weather && weather.temperature != null
        ? `<div style="font-size:9px;color:var(--text-dim);margin-top:1px;">${_weatherIcon(weather.weathercode, weather.is_day !== false)} ${Math.round(weather.temperature)}°C ${weather.description || ''}</div>`
        : '';
      
      html += `
        <div class="world-clock-item" onclick="openTimezonePicker(${idx})" style="gap: 8px;">
          ${analog}
          <div style="font-family: 'Courier New', monospace; font-size: 11px; color: var(--accent); letter-spacing: 1px; text-align: center; line-height: 1.3;">${digital}</div>
          <div class="zone" style="font-size: 11px;">${zone.city}</div>
          <div style="font-size: 10px; color: var(--text-dim);">${time.offsetLabel}</div>
          ${weatherHtml}
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
  _fetchClockWeather();
  
  setInterval(updateHomeTimeDisplay, 60000);
  setInterval(updateWorldClocks, 1000);
  setInterval(_fetchClockWeather, _WEATHER_CACHE_TTL);
  
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
  const currentTheme = _normalizeAtmosphereMode(window._selectedThemeMode || localStorage.getItem(FRIDAYS_THEME_MODE_KEY) || 'auto');
  const currentAtmosphereValue = _clampAtmosphereValue(
    document.getElementById('atmosphere-slider')?.value
    ?? localStorage.getItem(FRIDAYS_ATMOSPHERE_VALUE_KEY)
    ?? window._currentAtmosphereValue
    ?? 38
  );

  const settings = {
    time: currentTheme,
    atmosphereMode: currentTheme,
    foundationMode: _normalizeFoundationMode(localStorage.getItem(FRIDAYS_FOUNDATION_MODE_KEY) ?? 'auto'),
    atmosphereValue: currentAtmosphereValue,
    accentValue: _clampAtmosphereValue(document.getElementById('accent-slider')?.value ?? localStorage.getItem(FRIDAYS_ACCENT_VALUE_KEY) ?? 50),
    hueValue: _clampAtmosphereValue(document.getElementById('hue-slider')?.value ?? localStorage.getItem(FRIDAYS_HUE_VALUE_KEY) ?? 50),
    contrastValue: _clampAtmosphereValue(document.getElementById('contrast-slider')?.value ?? localStorage.getItem(FRIDAYS_CONTRAST_VALUE_KEY) ?? 58),
    glowValue: _clampAtmosphereValue(document.getElementById('glow-slider')?.value ?? localStorage.getItem(FRIDAYS_GLOW_VALUE_KEY) ?? 52),
    scene: _normalizeSceneMode(localStorage.getItem(FRIDAYS_SCENE_KEY) ?? 'beach'),
    sceneEffect: _normalizeSceneEffectMode(localStorage.getItem(FRIDAYS_SCENE_EFFECT_KEY) ?? 'on'),
    sceneLayers: _currentSceneLayers(),
    opacity: _clampTransparencyValue(document.getElementById('opacity-slider').value || '5'),
    setAsDefault: false,
  };

  localStorage.setItem('fridays-settings', JSON.stringify(settings));
  localStorage.setItem(FRIDAYS_THEME_MODE_KEY, currentTheme);
  localStorage.setItem(FRIDAYS_FOUNDATION_MODE_KEY, settings.foundationMode);
  localStorage.setItem(FRIDAYS_ATMOSPHERE_VALUE_KEY, String(Math.round(currentAtmosphereValue)));
  localStorage.setItem(FRIDAYS_ACCENT_VALUE_KEY, String(Math.round(settings.accentValue)));
  localStorage.setItem(FRIDAYS_HUE_VALUE_KEY, String(Math.round(settings.hueValue)));
  localStorage.setItem(FRIDAYS_CONTRAST_VALUE_KEY, String(Math.round(settings.contrastValue)));
  localStorage.setItem(FRIDAYS_GLOW_VALUE_KEY, String(Math.round(settings.glowValue)));
  localStorage.setItem(FRIDAYS_SCENE_KEY, settings.scene);
  localStorage.setItem(FRIDAYS_SCENE_EFFECT_KEY, settings.sceneEffect);
  localStorage.setItem(FRIDAYS_SCENE_LAYERS_KEY, JSON.stringify(settings.sceneLayers));
  showToast('Atmosphere saved', 'success');

  document.documentElement.style.setProperty('--glass-opacity', (100 - settings.opacity) / 100);
  applyTimeTheme(currentTheme, currentTheme === 'manual' ? currentAtmosphereValue : null);

  closeSettings();
}

function toggleSettings() {
  document.getElementById('settings-modal').classList.toggle('open');
}

function closeSettings() {
  document.getElementById('settings-modal').classList.remove('open');
}
