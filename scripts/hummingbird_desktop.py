#!/usr/bin/python3
"""Native Linux Hummingbird shell for the existing service; owns no backend."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import urllib.request
from urllib.parse import urlsplit
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import Gio, GLib, Gtk, WebKit2

ORIGIN = 'http://127.0.0.1:5050'

class Hummingbird(Gtk.Application):
    def __init__(self, receipt=None, conversation_id=None):
        super().__init__(application_id='local.hummingbird.Desktop', flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.receipt = receipt
        self.conversation_id = conversation_id
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.checking = False
        self.window = None
        self.loaded = False
        self.connect('activate', self.activate_window)
        self.connect('shutdown', lambda *_: self.pool.shutdown(wait=False, cancel_futures=True))

    def activate_window(self, *_):
        if self.window:
            self.window.present()
            return
        self.window = Gtk.ApplicationWindow(application=self, title='Hummingbird — APEX')
        self.window.set_default_size(1200, 820)
        self.window.set_icon_name('applications-internet')
        self.stack = Gtk.Stack()
        self.status = Gtk.Label(label='Connecting to Hummingbird…')
        self.status.set_line_wrap(True)
        self.stack.add_named(self.status, 'status')
        root = Path(GLib.get_user_data_dir()) / 'hummingbird' / 'webview'
        cache = Path(GLib.get_user_cache_dir()) / 'hummingbird' / 'webview'
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        cache.mkdir(parents=True, exist_ok=True, mode=0o700)
        data = WebKit2.WebsiteDataManager(base_data_directory=str(root), base_cache_directory=str(cache))
        context = WebKit2.WebContext.new_with_website_data_manager(data)
        cookies = context.get_cookie_manager()
        cookies.set_persistent_storage(str(root / 'cookies.sqlite'), WebKit2.CookiePersistentStorage.SQLITE)
        self.web = WebKit2.WebView.new_with_context(context)
        self.web.get_settings().set_enable_developer_extras(False)
        self.web.connect('decide-policy', self.navigation_policy)
        self.web.connect('load-changed', self.load_changed)
        self.web.connect('load-failed', self.load_failed)
        self.stack.add_named(self.web, 'chat')
        self.stack.set_visible_child_name('status')
        self.window.add(self.stack)
        self.window.show_all()
        self.check_backend()
        GLib.timeout_add_seconds(3, self.check_backend)
        if self.receipt:
            GLib.timeout_add_seconds(45, self.smoke_timeout)

    def navigation_policy(self, _view, decision, kind):
        if kind not in (WebKit2.PolicyDecisionType.NAVIGATION_ACTION, WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION):
            return False
        uri = decision.get_request().get_uri()
        parsed = urlsplit(uri)
        if parsed.scheme in ('about', 'data') or (parsed.scheme == 'http' and parsed.netloc == '127.0.0.1:5050'):
            return False
        decision.ignore()
        return True

    def check_backend(self):
        if self.loaded or self.checking:
            return True
        self.checking = True
        def probe():
            try:
                with urllib.request.urlopen(ORIGIN + '/api/health', timeout=2) as r:
                    return bool(json.load(r).get('ok'))
            except Exception:
                return False
        self.pool.submit(probe).add_done_callback(lambda f: GLib.idle_add(self.backend_result, f.result()))
        return True

    def backend_result(self, ready):
        self.checking = False
        if ready:
            self.loaded = True
            uri = ORIGIN + '/ui?app=hummingbird'
            if self.conversation_id:
                uri += '&conversation_id=' + str(self.conversation_id)
            self.web.load_uri(uri)
            self.stack.set_visible_child_name('chat')
        else:
            self.status.set_text('Hummingbird is starting. This window will reconnect automatically.')
        return False

    def load_failed(self, *_):
        self.loaded = False
        self.stack.set_visible_child_name('status')
        self.status.set_text('Hummingbird disconnected. Reconnecting…')
        return True

    def load_changed(self, _view, event):
        if event == WebKit2.LoadEvent.FINISHED and self.receipt:
            GLib.timeout_add_seconds(4, self.inspect_smoke)

    def inspect_smoke(self):
        script = """JSON.stringify({title:document.title,uri:location.href,mainChat:!!document.querySelector('#win-chat #question-input'),desktopMode:document.body.classList.contains('hummingbird-desktop'),errors:document.querySelectorAll('.error-overlay').length})"""
        self.web.evaluate_javascript(script, -1, None, None, None, self.smoke_result, None)
        return False

    def smoke_result(self, view, result, _data):
        try:
            value = json.loads(view.evaluate_javascript_finish(result).to_string())
            value['native_window_title'] = self.window.get_title()
            value['ok'] = value['mainChat'] and value['desktopMode'] and value['errors'] == 0
        except Exception as exc:
            value = {'ok': False, 'error': str(exc)}
        self.receipt.write_text(json.dumps(value, indent=2))
        print(json.dumps(value), flush=True)
        self.quit()

    def smoke_timeout(self):
        if self.receipt and not self.receipt.exists():
            self.receipt.write_text(json.dumps({'ok': False, 'error': 'native load timeout'}))
            self.quit()
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--smoke-receipt', type=Path)
    parser.add_argument('--conversation-id', type=int)
    args = parser.parse_args()
    if args.check:
        with urllib.request.urlopen(ORIGIN + '/api/health', timeout=5) as r:
            print(json.dumps({'ok': bool(json.load(r).get('ok')), 'gtk': Gtk.get_major_version(), 'webkit': WebKit2.get_major_version(), 'origin': ORIGIN}))
        return
    app = Hummingbird(args.smoke_receipt, args.conversation_id)
    app.run([])

if __name__ == '__main__':
    main()
