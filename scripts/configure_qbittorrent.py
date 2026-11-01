#!/usr/bin/env python3
"""Configure a closed qBittorrent 5.3+ for Fridays' authenticated local API."""
import base64
import argparse
import configparser
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', type=Path, help='Python 3.13+ executable for search plugins')
    args = parser.parse_args()
    if args.python:
        result = subprocess.run([str(args.python), '--version'], capture_output=True, text=True, check=True)
        version = tuple(int(part) for part in result.stdout.split()[1].split('.')[:2])
        if version < (3, 13):
            raise SystemExit('qBittorrent 5.3 search requires Python 3.13 or newer.')
    home = Path.home()
    directory = home / '.config/qBittorrent'
    if (directory / 'lockfile').exists():
        # qBittorrent's lock file persists; test the actual process instead.
        for proc in Path('/proc').iterdir():
            if proc.name.isdigit():
                try:
                    name = (proc / 'comm').read_text().strip()
                    owner = proc.stat().st_uid
                except (FileNotFoundError, PermissionError, ProcessLookupError):
                    continue
                if owner == home.stat().st_uid and name in {'qbittorrent', 'AppRun.wrapped', 'qbittorrent-nox'}:
                    raise SystemExit('Close qBittorrent before running setup.')
    path = directory / 'qBittorrent.conf'
    if not path.exists():
        raise SystemExit('Open qBittorrent once, then close it before running setup.')
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str
    config.read(path)
    password = secrets.token_urlsafe(36)
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha512', password.encode(), salt, 100000)
    if not config.has_section('WebUI'):
        config.add_section('WebUI')
    prefs = config['WebUI']
    prefs.update({
        'Enabled': 'true', 'Address': '127.0.0.1',
        'Port': '8085', 'Username': 'fridays',
        'Password_PBKDF2': '@ByteArray(' + base64.b64encode(salt).decode()
        + ':' + base64.b64encode(digest).decode() + ')',
        'LocalHostAuth': 'true', 'AuthSubnetWhitelistEnabled': 'false',
        'CSRFProtection': 'true', 'HostHeaderValidation': 'true',
        'ServerDomains': '"localhost;127.0.0.1"', 'UseUPnP': 'false',
    })
    config['BitTorrent']['Session\\DefaultSavePath'] = str(home / 'Downloads')
    if args.python:
        if not config.has_section('Preferences'):
            config.add_section('Preferences')
        config['Preferences']['Search\\pythonExecutablePath'] = str(args.python.resolve())
    backup = path.with_suffix('.conf.before-fridays')
    if not backup.exists():
        shutil.copy2(path, backup)
        backup.chmod(0o600)
    private_dir = home / '.config/swarm'
    private_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    credentials = private_dir / 'qbittorrent.json'
    # Create with private permissions before writing any secret.
    fd = open(credentials, 'w', opener=lambda p, flags: os.open(p, flags, 0o600))
    with fd:
        credentials.chmod(0o600)
        json.dump({'port': 8085, 'username': 'fridays', 'password': password}, fd)
    with path.open('w') as stream:
        config.write(stream, space_around_delimiters=False)
    print('Configured authenticated API at 127.0.0.1:8085. Downloads: ' + str(home / 'Downloads'))
    print('Reopen qBittorrent, then open Downloads in Fridays.')


if __name__ == '__main__':
    main()
