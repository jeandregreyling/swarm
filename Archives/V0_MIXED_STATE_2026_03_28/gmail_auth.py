"""
gmail_auth.py — Seven's Swarm
═══════════════════════════════════════════════════════════════════════════════
One-time OAuth2 setup for Gmail API + Pub/Sub.
Run this once: python3 gmail_auth.py
It opens a browser, Ghost approves, saves gmail_token.json.
After that, gmail_push.py uses the token automatically.
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
import os
sys.path.insert(0, '/home/seven/swarm')

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import json

CREDENTIALS_FILE = '/home/seven/swarm/gmail_credentials.json'
TOKEN_FILE       = '/home/seven/swarm/gmail_token.json'
PROJECT_ID       = 'gen-lang-client-0087469950'
TOPIC_NAME       = f'projects/{PROJECT_ID}/topics/gmail-push'

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.modify',
]


def get_credentials():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                print(f'\n✗ Missing: {CREDENTIALS_FILE}')
                print('  Download OAuth2 credentials from Cloud Console:')
                print('  APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID')
                print('  Application type: Desktop app → Download JSON → save as gmail_credentials.json\n')
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'w') as f:
            f.write(creds.to_json())
        print(f'\n✓ Token saved: {TOKEN_FILE}')
    return creds


def setup_gmail_watch(creds):
    from googleapiclient.discovery import build
    service = build('gmail', 'v1', credentials=creds)
    result = service.users().watch(
        userId='me',
        body={
            'topicName': TOPIC_NAME,
            'labelIds': ['INBOX'],
        }
    ).execute()
    print(f'✓ Gmail watch active. historyId: {result["historyId"]} | expires: {result["expiration"]}')
    return result


if __name__ == '__main__':
    print('\n=== Gmail Push Auth Setup ===\n')
    creds = get_credentials()
    print('✓ OAuth credentials valid.')
    result = setup_gmail_watch(creds)
    print('\n✓ Setup complete. gmail_push.py is ready to use.')
    print('  Run: python3 -c "from gmail_push import test; test()"')
