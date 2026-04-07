// Simple environment banner for UI
(function() {
  const stage = window.ENV_STAGE || 'unknown';
  const banner = document.createElement('div');
  banner.style.position = 'fixed';
  banner.style.top = '0';
  banner.style.left = '0';
  banner.style.width = '100%';
  banner.style.background = stage === '1' ? '#d32f2f' : (stage === '2' ? '#fbc02d' : '#388e3c');
  banner.style.color = '#fff';
  banner.style.textAlign = 'center';
  banner.style.zIndex = '9999';
  banner.style.fontWeight = 'bold';
  banner.style.padding = '4px 0';
  banner.innerText = stage === '1' ? 'PRODUCTION' : (stage === '2' ? 'UAT / PRE-PROD' : (stage === '3' ? 'DEV / SANDBOX' : 'UNKNOWN ENVIRONMENT'));
  document.body.appendChild(banner);
})();
