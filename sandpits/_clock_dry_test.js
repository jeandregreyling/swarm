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

