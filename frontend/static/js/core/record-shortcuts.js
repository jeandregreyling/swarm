// Shared "jump into Platinum surfaces" helpers, callable from any tile.
//   openRecord(kind, id)     -> opens Studio, switches to Records tab, selects the record
//   revealInFiles(kind, id)  -> opens the Files tile and navigates to the kind/yyyy/mm folder
//
// Both helpers degrade gracefully if the target tile/window is not yet mounted.

(function () {
  function _openWindow(winId, title, templateId) {
    if (typeof openWindow === 'function') {
      try { openWindow(winId, title, templateId); return true; } catch (e) {}
    }
    if (typeof window.openWindow === 'function') {
      try { window.openWindow(winId, title, templateId); return true; } catch (e) {}
    }
    return false;
  }

  function openRecord(kind, id) {
    if (!kind || !id) return;
    _openWindow('studio', 'Studio', 'view-studio');
    // Studio mounts asynchronously; poll for studioSetTab and the records loader.
    let tries = 0;
    const tick = () => {
      tries++;
      if (typeof studioSetTab === 'function') {
        try { studioSetTab('records'); } catch (e) {}
      }
      if (typeof loadStudioRecordsPanel === 'function') {
        try { loadStudioRecordsPanel(); } catch (e) {}
      }
      // Studio Records panel exposes _selectRecord on window once bootstrapped.
      if (typeof window.studioRecordsSelect === 'function') {
        try { window.studioRecordsSelect(kind, id); return; } catch (e) {}
      }
      if (tries < 20) setTimeout(tick, 150);
    };
    setTimeout(tick, 200);
  }

  function revealInFiles(kind, id) {
    if (!kind) return;
    _openWindow('records-files', 'Files', 'view-records-files');
    // The Files tile lives in runtime/records/<kind>/<yyyy>/<mm>/<id>.json — but we don't
    // know the year/month without a probe. Easiest: navigate to <kind>/, let the user drill in.
    // (When opening a known record, the Files tile detail pane in the Records tab already shows
    //  the absolute json_path with a vscode://file link.)
    let tries = 0;
    const tick = () => {
      tries++;
      if (typeof window.recordsFilesNavigate === 'function') {
        try { window.recordsFilesNavigate(kind); return; } catch (e) {}
      }
      if (tries < 20) setTimeout(tick, 150);
    };
    setTimeout(tick, 200);
  }

  window.openRecord = openRecord;
  window.revealInFiles = revealInFiles;
})();
