<<<CONTENT>>>
    // Banner rendering, animation, interactions
    function renderFridaysBanner() {
      const banner = document.createElement('div');
      banner.className = 'fridays-banner';
      banner.innerHTML = `
        <div class="fridays-temp" id="system-temp"></div>
        <button class="fridays-banner-btn" id="fridays-btn-status">Status</button>
        <button class="fridays-banner-btn" id="fridays-btn-agents">Agents</button>
        <button class="fridays-banner-btn" id="fridays-btn-skills">Skills</button>
      `;
      document.body.prepend(banner);