"""
gmail_push.py — Seven's Swarm
═══════════════════════════════════════════════════════════════════════════════
Gmail Push Notifications via Google Cloud Pub/Sub. (RL-011)
Replaces the 60-second IMAP poll in listener.py.

How it works:
  1. Gmail watches the INBOX and publishes a notification to Pub/Sub when
     a new message arrives.
  2. pull_new_emails() subscribes (pull model — no public endpoint needed)
     and blocks until a notification arrives or timeout.
  3. On notification, fetches the new message(s) via Gmail API.
  4. Returns a list of email dicts in the same format as check_gmail() —
     listener.py needs zero changes to the processing logic.

Watch renewal:
  Gmail watch() expires every 7 days. renew_watch_if_needed() is called
  at startup and checked daily. It silently renews when within 24h of expiry.
═══════════════════════════════════════════════════════════════════════════════
"""

import os
import sys
import base64
import json
import logging
import time
from datetime import datetime, timezone

_SWARM_ROOT = os.environ.get('SWARM_ROOT') or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _SWARM_ROOT)

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from google.cloud import pubsub_v1

logger = logging.getLogger('seven.gmail_push')

TOKEN_FILE       = os.path.join(_SWARM_ROOT, 'lib', 'email', 'gmail_token.json')
WATCH_STATE_FILE = os.path.join(_SWARM_ROOT, 'lib', 'email', 'gmail_watch_state.json')
PROJECT_ID       = 'gen-lang-client-0087469950'
TOPIC_NAME       = f'projects/{PROJECT_ID}/topics/gmail-push'
SUBSCRIPTION     = f'projects/{PROJECT_ID}/subscriptions/gmail-push-sub'

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.modify',
]


# ── Credentials ──────────────────────────────────────────────────────────────

def _get_creds():
    if not os.path.exists(TOKEN_FILE):
        raise RuntimeError(
            f'Gmail token not found: {TOKEN_FILE}\n'
            'Run: python3 gmail_auth.py'
        )
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, 'w') as f:
            f.write(creds.to_json())
    return creds


def _gmail_service():
    return build('gmail', 'v1', credentials=_get_creds())


# ── Watch management ─────────────────────────────────────────────────────────

def renew_watch_if_needed():
    """
    Renew Gmail watch if it expires within 24 hours (or hasn't been set up).
    Gmail watch expires every 7 days — must be renewed to keep push active.
    """
    now_ms = int(time.time() * 1000)
    expiry_ms = 0

    if os.path.exists(WATCH_STATE_FILE):
        with open(WATCH_STATE_FILE) as f:
            state = json.load(f)
        expiry_ms = int(state.get('expiration', 0))

    # Renew if expiring within 24 hours or not set
    if expiry_ms - now_ms < 86_400_000:
        service = _gmail_service()
        result = service.users().watch(
            userId='me',
            body={'topicName': TOPIC_NAME, 'labelIds': ['INBOX']}
        ).execute()
        with open(WATCH_STATE_FILE, 'w') as f:
            json.dump(result, f)
        exp_readable = datetime.fromtimestamp(int(result['expiration']) / 1000).strftime('%Y-%m-%d %H:%M')
        logger.info(f'[Gmail Push] Watch renewed. Expires: {exp_readable}')
        print(f'[Gmail Push] Watch renewed. Expires: {exp_readable}')
    else:
        exp_readable = datetime.fromtimestamp(expiry_ms / 1000).strftime('%Y-%m-%d %H:%M')
        logger.debug(f'[Gmail Push] Watch valid until {exp_readable}')


# ── Message fetching ──────────────────────────────────────────────────────────

def _fetch_messages_since(service, history_id):
    """
    Fetch new messages using Gmail history API from the given historyId.
    Returns list of message IDs.
    """
    try:
        history = service.users().history().list(
            userId='me',
            startHistoryId=history_id,
            historyTypes=['messageAdded'],
            labelId='INBOX',
        ).execute()
    except Exception as e:
        logger.warning(f'[Gmail Push] History fetch failed: {e}')
        return []

    message_ids = []
    for record in history.get('history', []):
        for added in record.get('messagesAdded', []):
            msg = added.get('message', {})
            labels = msg.get('labelIds', [])
            if 'INBOX' in labels and 'SPAM' not in labels and 'TRASH' not in labels:
                message_ids.append(msg['id'])
    return message_ids


def _parse_message(service, msg_id):
    """
    Fetch a Gmail message by ID and return a dict matching check_gmail() format.
    """
    try:
        msg = service.users().messages().get(
            userId='me', id=msg_id, format='full'
        ).execute()
    except Exception as e:
        logger.warning(f'[Gmail Push] Could not fetch message {msg_id}: {e}')
        return None

    headers = {h['name'].lower(): h['value'] for h in msg['payload'].get('headers', [])}
    subject = headers.get('subject', '(no subject)')
    from_raw = headers.get('from', '')
    message_id_header = headers.get('message-id', '')
    date = headers.get('date', '')

    # Extract sender email
    import re
    match = re.search(r'<(.+?)>', from_raw)
    sender = match.group(1).lower() if match else from_raw.lower().strip()

    # Extract body
    body = _extract_body(msg['payload'])

    # Mark as read
    try:
        service.users().messages().modify(
            userId='me',
            id=msg_id,
            body={'removeLabelIds': ['UNREAD']}
        ).execute()
    except Exception:
        pass

    return {
        'id':         msg_id,
        'from':       sender,
        'from_raw':   from_raw,
        'subject':    subject,
        'body':       body,
        'date':       date,
        'message_id': message_id_header,
    }


def _extract_body(payload):
    """Recursively extract plain text from Gmail message payload."""
    if payload.get('mimeType') == 'text/plain':
        data = payload.get('body', {}).get('data', '')
        if data:
            return base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')

    for part in payload.get('parts', []):
        result = _extract_body(part)
        if result:
            return result

    return ''


# ── Main pull loop ────────────────────────────────────────────────────────────

def pull_new_emails(timeout_seconds=55):
    """
    Pull Pub/Sub for Gmail notifications. Blocks up to timeout_seconds.
    Returns a list of email dicts (same format as check_gmail()).
    Called in a loop by listener.py instead of check_gmail() + sleep(60).
    """
    # Pass OAuth2 credentials explicitly — Pub/Sub client won't find ADC in a systemd service
    creds = _get_creds()
    subscriber = pubsub_v1.SubscriberClient(credentials=creds)
    emails = []

    try:
        response = subscriber.pull(
            request={
                'subscription': SUBSCRIPTION,
                'max_messages': 10,
            },
            timeout=timeout_seconds,
        )
    except Exception as e:
        logger.debug(f'[Gmail Push] Pull timeout or error: {e}')
        return []

    if not response.received_messages:
        return []

    ack_ids = []
    history_ids = []

    for received in response.received_messages:
        ack_ids.append(received.ack_id)
        try:
            data = json.loads(received.message.data.decode('utf-8'))
            history_id = data.get('historyId')
            if history_id:
                history_ids.append(str(history_id))
        except Exception as e:
            logger.warning(f'[Gmail Push] Could not parse Pub/Sub message: {e}')

    # Acknowledge all received messages
    if ack_ids:
        try:
            subscriber.acknowledge(
                request={'subscription': SUBSCRIPTION, 'ack_ids': ack_ids}
            )
        except Exception as e:
            logger.warning(f'[Gmail Push] Ack failed: {e}')

    if not history_ids:
        return []

    # Use the lowest historyId to fetch all new messages since
    min_history_id = min(history_ids, key=lambda x: int(x))
    service = _gmail_service()
    msg_ids = _fetch_messages_since(service, min_history_id)

    for msg_id in msg_ids:
        email = _parse_message(service, msg_id)
        if email:
            emails.append(email)
            logger.info(f'[Gmail Push] New email from {email["from"]}: {email["subject"]}')

    return emails


# ── Test ──────────────────────────────────────────────────────────────────────

def test():
    print('\n[Gmail Push] Testing connection...')
    try:
        creds = _get_creds()
        service = _gmail_service()
        profile = service.users().getProfile(userId='me').execute()
        print(f'✓ Gmail API connected: {profile["emailAddress"]}')
        print(f'  Messages total: {profile["messagesTotal"]}')
        renew_watch_if_needed()
        print('✓ gmail_push.py ready.')
    except Exception as e:
        print(f'✗ {e}')


if __name__ == '__main__':
    test()
