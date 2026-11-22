// hb-ui-discover.js
// Provides a read‑only capability to discover the top ribbon UI elements.
// This module exports a single function that returns a static description
// of the ribbon controls, including provenance information.

module.exports = {
  discoverRibbon: async function() {
    try {
      const resp = await fetch('/api/peer/v1/hb/live');
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      // The snapshot contains a `lanes` field with the controls list.
      const lanes = data.lanes || [];
      return {
        title: 'HB Live Ribbon',
        provenance: 'frontend/static/js/hb-live.js',
        controls: lanes.map(ctrl => ({
          id: ctrl.id,
          label: ctrl.label,
          description: ctrl.description || ''
        }))
      };
    } catch (e) {
      console.error('hb-ui-discover: failed to fetch lanes', e);
      return {
        title: 'HB Live Ribbon',
        provenance: 'frontend/static/js/hb-live.js',
        controls: []
      };
    }
  },
  // Expose a generic attached‑tool entry point
  ui_discover: async function() {
    return await this.discoverRibbon();
  },
  // Register this tool with the attached‑tool dispatcher
  register: function(dispatcher) {
    dispatcher.register('ui_discover', this.ui_discover.bind(this));
  }
};

// Export the module for the dispatcher to load
module.exports = module.exports;
