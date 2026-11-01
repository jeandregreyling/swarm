function loadDownloadsData(win) {
  const root = win.el.querySelector('.downloads-panel');
  const el = name => root.querySelector(`[data-dl="${name}"]`);
  let searchId = null;
  let disposed = false;
  let refreshTimer = null;
  let searchTimer = null;
  let refreshing = false;
  const error = err => { el('error').textContent = err.message; };
  const api = async (path = '', options = {}) => {
    const response = await fetch('/api/downloads' + path, options);
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || `Downloads request failed (${response.status})`);
    return data;
  };
  const post = (path, data) => api(path, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data),
  });
  const bytes = number => {
    if (!Number.isFinite(number) || number < 0) return '-';
    const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];
    let index = 0;
    while (number >= 1024 && index < units.length - 1) { number /= 1024; index++; }
    return `${number.toFixed(index ? 1 : 0)} ${units[index]}`;
  };
  const button = (label, handler) => {
    const node = document.createElement('button');
    node.type = 'button';
    node.textContent = label;
    node.addEventListener('click', async () => {
      node.disabled = true;
      el('error').textContent = '';
      try { await handler(); } catch (err) { error(err); } finally { node.disabled = false; }
    });
    return node;
  };
  async function openQbittorrent() {
    el('launch-status').textContent = 'Opening qBittorrent...';
    try {
      await post('/open-qbittorrent', {});
      el('launch-status').textContent = 'qBittorrent is ready. Manage transfers below; its desktop window opens separately.';
      await refresh();
    } catch (err) {
      el('launch-status').textContent = '';
      throw err;
    }
  }
  const table = (target, headings) => {
    target.replaceChildren();
    const node = document.createElement('table');
    node.style.cssText = 'width:100%;border-collapse:collapse;text-align:left;';
    const head = node.createTHead().insertRow();
    headings.forEach(label => { const th = document.createElement('th'); th.textContent = label; head.append(th); });
    target.append(node);
    return node.createTBody();
  };
  const cell = (row, text) => {
    const node = row.insertCell();
    node.style.cssText = 'padding:8px 6px;border-bottom:1px solid var(--border);';
    node.textContent = text;
    return node;
  };
  async function refresh() {
    if (refreshing || disposed) return;
    refreshing = true;
    try {
      const data = await api();
      if (disposed) return;
      el('path').textContent = data.download_dir;
      const t = data.transfer;
      el('connection').textContent = `qBittorrent ${data.version} | ${t.connection_status} | DHT nodes: ${t.dht_nodes} | Down: ${bytes(t.dl_info_speed)}/s | Up: ${bytes(t.up_info_speed)}/s`;
      const plugins = data.plugins.filter(p => p.enabled).map(p => p.fullName || p.name);
      el('engines').textContent = plugins.length ? `Enabled engines: ${plugins.join(', ')}` :
        'No enabled engines. In qBittorrent: View > Search Engine, then Search plugins to install/enable one.';
      const body = table(el('torrents'), ['Torrent', 'Progress / state', 'Speed / ETA', 'Seeds / peers', 'Controls']);
      data.torrents.forEach(torrent => {
        const row = body.insertRow();
        cell(row, torrent.name);
        cell(row, `${(torrent.progress * 100).toFixed(1)}% / ${torrent.state}`);
        cell(row, `${bytes(torrent.dlspeed)}/s / ${torrent.eta < 8640000 ? Math.ceil(torrent.eta / 60) + ' min' : 'unknown'}`);
        cell(row, `${torrent.num_seeds} (${torrent.num_complete} reported) / ${torrent.num_leechs}`);
        const controls = cell(row, '');
        ['start', 'stop', 'reannounce', 'remove'].forEach(action => {
          controls.append(button({start: 'Resume', stop: 'Pause', reannounce: 'Find peers', remove: 'Remove task'}[action], async () => {
            if (action === 'remove' && !confirm(`Remove "${torrent.name}" from qBittorrent? Downloaded files will be kept.`)) return;
            await post('/action', {hash: torrent.hash, action});
            await refresh();
          }));
        });
        controls.append(button('Trackers', async () => {
          const data = await api(`/${encodeURIComponent(torrent.hash)}/trackers`);
          el('trackers').textContent = torrent.name + '\n' + data.trackers.map(t =>
            `${t.url}: ${t.msg || 'status ' + t.status} | seeds ${t.num_seeds} | peers ${t.num_peers}`
          ).join('\n');
        }));
      });
      if (!data.torrents.length) el('torrents').textContent = 'No torrents yet. Search below or add a magnet / .torrent file.';
    } catch (err) {
      el('connection').textContent = 'qBittorrent unavailable';
      error(err);
    } finally { refreshing = false; }
  }
  async function listFiles() {
    const data = await api('/files');
    el('files').replaceChildren();
    data.files.forEach(file => {
      const item = document.createElement('li');
      item.textContent = file.name + (file.directory ? ' (folder)' : ' - ' + bytes(file.size));
      if (file.qbittorrent) item.append(' ', button('Open qBittorrent', openQbittorrent));
      if (file.windows) {
        item.append(' ', button('Run in Bottles', async () => {
          if (!confirm(`Run "${file.name}" with Wine in the Fridays bottle? Only run Windows programs you trust.`)) return;
          await post('/run-windows', {name: file.name});
          el('error').textContent = `Starting "${file.name}" in Bottles; its window opens on your desktop.`;
        }));
      }
      el('files').append(item);
    });
    if (!data.files.length) el('files').textContent = 'Downloads folder is empty.';
  }
  async function clearSearch() {
    clearTimeout(searchTimer);
    const id = searchId;
    searchId = null;
    el('cancel').disabled = true;
    if (id !== null) await api(`/search/${id}`, {method: 'DELETE'});
  }
  async function pollSearch(id) {
    if (disposed || id !== searchId) return;
    try {
      const data = await api(`/search/${id}`);
      if (disposed || id !== searchId) return;
      const body = table(el('results'), ['Result', 'Size', 'Seeds / leechers', 'Engine', 'Download']);
      data.results.forEach(result => {
        const row = body.insertRow();
        cell(row, result.fileName);
        cell(row, bytes(result.fileSize));
        cell(row, `${result.nbSeeders} / ${result.nbLeechers}`);
        cell(row, result.siteUrl);
        const controls = cell(row, '');
        if (result.fileUrl.startsWith('magnet:')) {
          controls.append(button('Download', async () => {
            await post('/add', {magnet: result.fileUrl});
            await refresh();
          }));
        } else {
          const url = result.descrLink || result.fileUrl;
          if (/^https?:\/\//i.test(url)) {
            const link = document.createElement('a');
            link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer';
            link.textContent = 'Source / .torrent';
            controls.append(link);
          }
        }
      });
      const running = data.searches.some(item => item.status === 'Running');
      el('search-status').textContent = `${running ? 'Searching' : 'Finished'}: ${data.total} result(s), showing up to 100.` +
        (!running && !data.total ? ' No results does not mean your connection is broken; the engine may be unavailable or have no matches.' : '');
      if (running) searchTimer = setTimeout(() => pollSearch(id), 2000);
      else await clearSearch();
    } catch (err) { error(err); }
  }
  el('add-form').onsubmit = async event => {
    event.preventDefault();
    try {
      await post('/add', {magnet: event.target.elements.magnet.value});
      event.target.reset(); el('error').textContent = ''; await refresh();
    } catch (err) { error(err); }
  };
  el('upload-form').onsubmit = async event => {
    event.preventDefault();
    try {
      await api('/add', {method: 'POST', body: new FormData(event.target)});
      event.target.reset(); el('error').textContent = ''; await refresh();
    } catch (err) { error(err); }
  };
  el('search-form').onsubmit = async event => {
    event.preventDefault();
    const submit = event.target.querySelector('[type="submit"]');
    submit.disabled = true;
    try {
      await clearSearch();
      el('error').textContent = '';
      const data = await post('/search', {query: event.target.elements.query.value});
      searchId = data.id;
      el('cancel').disabled = false;
      await pollSearch(searchId);
    } catch (err) { error(err); } finally { submit.disabled = false; }
  };
  el('cancel').onclick = () => clearSearch().then(() => {
    el('search-status').textContent = 'Search cancelled.';
  }).catch(error);
  el('refresh').onclick = refresh;
  el('open-qbittorrent').onclick = async () => {
    const control = el('open-qbittorrent');
    control.disabled = true;
    el('error').textContent = '';
    try { await openQbittorrent(); } catch (err) { error(err); } finally { control.disabled = false; }
  };
  el('files-button').onclick = () => listFiles().catch(error);
  // Window removal owns timer cleanup, including searches still running in qBittorrent.
  const observer = new MutationObserver(() => {
    if (!win.el.isConnected) {
      disposed = true;
      clearInterval(refreshTimer);
      clearSearch().catch(error);
      observer.disconnect();
    }
  });
  observer.observe(win.el.parentNode, {childList: true});
  refresh();
  listFiles().catch(error);
  refreshTimer = setInterval(refresh, 5000);
}
