// env-banner.js — Fixed version
(function() {
  // Wait for DOM + possible ENV_STAGE injection from Flask
  function createBanner() {
    const stage = (window.ENV_STAGE || document.body?.dataset?.stage || 'unknown').toUpperCase();
    
    const banner = document.createElement('div');
    banner.id = 'env-banner';
    banner.style.cssText = `
      position: fixed; top: 0; left: 0; right: 0; z-index: 99999;
      padding: 4px 0; text-align: center; font-weight: 700; font-size: 11px;
      color: white; letter-spacing: 0.5px;
      background: ${stage === 'PROD' ? '#d32f2f' : stage === 'UAT' ? '#f57c00' : '#388e3c'};
    `;
    banner.textContent = stage === 'PROD' ? 'PRODUCTION' : 
                         stage === 'UAT' ? 'UAT / WEDNESDAY' : 
                         stage === 'DEV' ? 'DEV / MONDAY' : `ENV: ${stage}`;
    
    document.body.prepend(banner);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', createBanner);
  } else {
    createBanner();
  }
})();