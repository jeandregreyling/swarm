/* Owner-only proposal review. No decision is sent without an explicit button click. */
(function () {
  'use strict';

  let panel = null;
  let loading = false;
  let refreshAgain = false;

  function make(tag, text) {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function showError(message) {
    if (typeof showToast === 'function') showToast(message, 'error');
    console.error('[Tool approval]', message);
  }

  function render(transactions) {
    if (!panel) {
      panel = make('section');
      panel.id = 'tool-approval-panel';
      panel.setAttribute('aria-label', 'APEX tool approvals');
      panel.style.cssText = 'position:fixed;right:20px;bottom:20px;z-index:20000;' +
        'width:min(700px,95vw);max-height:85vh;overflow:auto;padding:16px;' +
        'background:var(--bg-card,#fff);color:var(--text,#172033);' +
        'border:2px solid #d69b25;border-radius:12px;box-shadow:0 8px 32px #0005;';
      document.body.appendChild(panel);
    }
    panel.replaceChildren();
    panel.hidden = transactions.length === 0;
    transactions.forEach(transaction => {
      const card = make('article');
      card.dataset.transactionId = transaction.transaction_id;
      card.appendChild(make('h3', 'APEX is paused: human approval required'));
      card.appendChild(make('p', transaction.tool + ' | Chat #' + transaction.conversation_id));
      card.appendChild(make('p', 'Transaction: ' + transaction.transaction_id));
      card.appendChild(make('p', 'Targets: ' + transaction.paths.join(', ')));
      card.appendChild(make('p', 'Expires: ' + new Date(transaction.expires_at * 1000).toLocaleString()));
      if (transaction.message) card.appendChild(make('p', 'Commit message: ' + transaction.message));
      const diff = make('pre', transaction.diff);
      diff.style.cssText = 'max-height:40vh;overflow:auto;white-space:pre-wrap;' +
        'font:12px monospace;padding:10px;background:#8881;';
      card.appendChild(diff);
      const status = make('p', 'No changes have executed. Review the entire diff before approving.');
      status.setAttribute('role', 'status');
      card.appendChild(status);
      const approve = make('button', 'Approve');
      const reject = make('button', 'Reject');
      approve.type = reject.type = 'button';
      approve.style.marginRight = '12px';

      async function decide(decision) {
        approve.disabled = reject.disabled = true;
        status.textContent = decision ? 'Submitting approval and checking for drift...' : 'Rejecting proposal...';
        try {
          const response = await fetch('/api/tool-approval', {
            method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-Tool-Approval-CSRF': transaction.csrf_token },
            body: JSON.stringify({ transaction_id: transaction.transaction_id, decision: decision })
          });
          const data = await response.json();
          if (!response.ok || !data.ok) throw new Error(
            data.error || data.receipt?.output || 'Approval request failed (' + response.status + ')');
          status.textContent = data.receipt.output;
          await refresh();
        } catch (error) {
          status.textContent = error.message;
          showError(error.message);
          // Refresh only on explicit events; never retry a mutation automatically.
          approve.disabled = reject.disabled = false;
        }
      }
      approve.addEventListener('click', () => decide(true));
      reject.addEventListener('click', () => decide(false));
      card.append(approve, reject);
      panel.appendChild(card);
    });
  }

  async function refresh() {
    if (loading) {
      refreshAgain = true;
      return;
    }
    loading = true;
    try {
      const response = await fetch('/api/tool-approval', { credentials: 'same-origin', cache: 'no-store' });
      if (response.status === 401) {
        if (panel) panel.hidden = true;
        return;
      }
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || 'Unable to load pending tool approvals');
      render(data.pending);
    } catch (error) {
      showError(error.message);
    } finally {
      loading = false;
      if (refreshAgain) {
        refreshAgain = false;
        refresh();
      }
    }
  }

  document.addEventListener('sse:tool_approval_pending', refresh);
  document.addEventListener('sse:connected', refresh);
  document.addEventListener('sse:chat', event => {
    if (event.detail?.status === 'tool_receipt') refresh();
  });
  window.addEventListener('DOMContentLoaded', refresh);
})();
