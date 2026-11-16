#!/usr/bin/python3
"""HB secure credentials window (owner 15 Nov 2026): a small glowing-gold window where JD types a user ID and password himself.

What is typed goes straight from this window into the system keyring (GNOME Keyring / libsecret: encrypted on disk, unlocked by
JD's login). It is never printed, never written to a file or the HB database, never put in chat, and no model or agent sees it.
The only thing this script prints is one line saying whether something was saved.

    hb_secure_creds.py [--name sap] [--title "SAP"]     open the window
    hb_secure_creds.py --status [--name sap]            say whether an entry exists (never shows it)
    hb_secure_creds.py --forget [--name sap]            delete the entry

HB code reads it later with read(name) -> (user_id, password, system) - only at the moment a real login needs it."""
import argparse
import json
import sys

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('Secret', '1')
from gi.repository import Gtk, Gdk, GLib, Secret

SCHEMA = Secret.Schema.new('local.hummingbird.Credentials', Secret.SchemaFlags.NONE, {'name': Secret.SchemaAttributeType.STRING})
CSS = b"""
#hb-creds { background: #14110a; border: 2px solid #d4af37; border-radius: 14px; animation: hb-gold 2.4s ease-in-out infinite; }
@keyframes hb-gold { 0% { box-shadow: 0 0 6px 1px rgba(212,175,55,.45); border-color: #b8962e; }
                     50% { box-shadow: 0 0 26px 6px rgba(255,215,0,.85); border-color: #ffd700; }
                     100% { box-shadow: 0 0 6px 1px rgba(212,175,55,.45); border-color: #b8962e; } }
#hb-creds label { color: #f3e3a8; }
#hb-creds #title { color: #ffd700; font-size: 17px; font-weight: 700; }
#hb-creds #note { color: #bfae78; font-size: 11px; }
#hb-creds entry { background: #1d180d; color: #fff3c4; border: 1px solid #8a7430; border-radius: 6px; padding: 6px; caret-color: #ffd700; }
#hb-creds entry:focus { border-color: #ffd700; box-shadow: 0 0 6px rgba(255,215,0,.6); }
#hb-creds button { background: #2a220f; color: #ffd700; border: 1px solid #d4af37; border-radius: 6px; padding: 6px 14px; }
#hb-creds button#save { background: #d4af37; color: #14110a; font-weight: 700; }
"""


def read(name='sap'):
    """(user_id, password, system) from the keyring, or None. For HB code at the moment of a real login - never log the result."""
    raw = Secret.password_lookup_sync(SCHEMA, {'name': name}, None)
    if not raw:
        return None
    data = json.loads(raw)
    return data.get('user', ''), data.get('password', ''), data.get('system', '')


def exists(name='sap'):
    return Secret.password_lookup_sync(SCHEMA, {'name': name}, None) is not None


def forget(name='sap'):
    return Secret.password_clear_sync(SCHEMA, {'name': name}, None)


def _store(name, title, user, password, system):
    return Secret.password_store_sync(SCHEMA, {'name': name}, Secret.COLLECTION_DEFAULT, f'Hummingbird: {title} login',
                                      json.dumps({'user': user, 'password': password, 'system': system}), None)


class Window(Gtk.Window):
    def __init__(self, name, title):
        super().__init__(title=f'Hummingbird - secure credentials ({title})')
        self.name, self.label, self.saved = name, title, False
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_default_size(440, -1)
        self.set_app_paintable(True)
        visual = self.get_screen().get_rgba_visual()
        if visual:
            self.set_visual(visual)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        outer = Gtk.Box(margin=30)                      # room for the glow
        frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        frame.set_name('hb-creds')
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=20)
        head = Gtk.Label(label=f'🔐 {title} login - secure entry', xalign=0)
        head.set_name('title')
        note = Gtk.Label(xalign=0, wrap=True, max_width_chars=52,
                         label='Typed here, it goes straight into your system keyring (encrypted, unlocked by your login). '
                               'It is not shown in chat, not saved in HB, and no model sees it.')
        note.set_name('note')
        self.system = Gtk.Entry(placeholder_text='System / client (optional), e.g. PRD 100 or the logon URL')
        self.user = Gtk.Entry(placeholder_text=f'{title} user ID')
        self.password = Gtk.Entry(placeholder_text='Password', visibility=False, input_purpose=Gtk.InputPurpose.PASSWORD)
        self.password.set_invisible_char('●')
        self.password.connect('activate', self.save)
        self.message = Gtk.Label(xalign=0)
        self.message.set_name('note')
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label='Cancel')
        cancel.connect('clicked', lambda *_: self.close())
        save = Gtk.Button(label='Save to keyring')
        save.set_name('save')
        save.connect('clicked', self.save)
        buttons.pack_start(cancel, False, False, 0)
        buttons.pack_start(save, False, False, 0)
        for widget in (head, note, self.system, self.user, self.password, self.message, buttons):
            inner.pack_start(widget, False, False, 0)
        frame.pack_start(inner, True, True, 0)
        outer.pack_start(frame, True, True, 0)
        self.add(outer)
        self.connect('key-press-event', lambda _w, e: e.keyval == Gdk.KEY_Escape and self.close())
        self.connect('destroy', Gtk.main_quit)
        if exists(name):
            self.message.set_text('An entry is already saved; saving again replaces it.')
        self.show_all()
        self.present()
        self.user.grab_focus()

    def save(self, *_):
        user, password = self.user.get_text().strip(), self.password.get_text()
        if not user or not password:
            self.message.set_text('Both the user ID and the password are needed.')
            return
        try:
            ok = _store(self.name, self.label, user, password, self.system.get_text().strip())
        except GLib.Error as exc:
            self.message.set_text(f'The keyring refused it: {exc.message}')
            return
        self.password.set_text('')
        if ok:
            self.saved = True
            self.close()
        else:
            self.message.set_text('The keyring did not save it.')


def main():
    parser = argparse.ArgumentParser(description='HB secure credentials window')
    parser.add_argument('--name', default='sap')
    parser.add_argument('--title', default='SAP')
    parser.add_argument('--status', action='store_true')
    parser.add_argument('--forget', action='store_true')
    args = parser.parse_args()
    if args.status:
        print(f"{args.name}: {'saved in the keyring' if exists(args.name) else 'nothing saved'}")
        return 0
    if args.forget:
        print(f"{args.name}: {'deleted' if forget(args.name) else 'nothing to delete'}")
        return 0
    window = Window(args.name, args.title)
    Gtk.main()
    print(f"{args.name}: {'saved in the keyring' if window.saved else 'closed without saving'}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
