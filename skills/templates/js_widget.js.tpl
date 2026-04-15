/**
 * {{TOOL_NAME}} — {{DESCRIPTION}}
 * Built by {{AGENT}} on {{DATE}}
 */

(function() {
    'use strict';

    function init() {
        console.log('{{TOOL_NAME}} widget initialised');
        // TODO: implement widget logic here
    }

    function render(container) {
        if (!container) return;
        container.innerHTML = '<div class="widget-{{TOOL_NAME}}">{{TOOL_NAME}} widget</div>';
    }

    // Auto-init if DOM ready
    if (typeof document !== 'undefined') {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', init);
        } else {
            init();
        }
    }

    // Export for testing
    if (typeof module !== 'undefined') {
        module.exports = { init, render };
    }
})();
