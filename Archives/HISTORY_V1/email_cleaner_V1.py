import re

# Patterns that indicate the start of a quoted reply chain
QUOTE_MARKERS = [
    '________________________________',
    '-----Original Message-----',
    '-----Forwarded Message-----',
    'From:',
    '> ',
    'Sent from my',
]

# BUG-007 fix: 'On ' was too broad — "On the topic of..." would get truncated.
# Gmail/Outlook quoted headers always end with 'wrote:'. Match that pattern only.
_GMAIL_QUOTE_RE = re.compile(r'^On .+ wrote:$', re.IGNORECASE)

# Patterns that indicate start of email signature
SIGNATURE_MARKERS = [
    'Kind regards',
    'kind regards',
    'Regards,',
    'regards,',
    'Thanks,',
    'thanks,',
    'Thank you,',
    'Cheers,',
    'cheers,',
    'Best,',
    'best,',
    'Best regards',
    'Warm regards',
    'Yours sincerely',
    'Sent from my iPhone',
    'Sent from my Samsung',
    'Sent from Outlook',
    '--',
    '-- ',
]

def strip_email_body(body):
    if not body:
        return ''

    lines = body.split('\n')
    clean_lines = []

    for line in lines:
        stripped = line.strip()

        # Check for quote markers - stop here
        quote_found = False
        for marker in QUOTE_MARKERS:
            if stripped.startswith(marker):
                quote_found = True
                break
        # BUG-007 fix: Gmail quote header ends with 'wrote:' — safe pattern
        if not quote_found and _GMAIL_QUOTE_RE.match(stripped):
            quote_found = True
        if quote_found:
            break

        # Check for signature markers - stop here
        sig_found = False
        for marker in SIGNATURE_MARKERS:
            if stripped.startswith(marker):
                sig_found = True
                break
        if sig_found:
            break

        clean_lines.append(line)

    # Join and strip trailing whitespace
    result = '\n'.join(clean_lines).strip()

    # If we stripped everything, return original truncated
    if not result:
        return body[:500].strip()

    return result

def extract_subject_question(subject, body):
    clean_body = strip_email_body(body)

    # If body is empty or very short, the subject IS the question
    if not clean_body or len(clean_body) < 10:
        return subject

    # Prepend subject only when it adds context.
    # e.g. subject "Humpty Dumpty" + body "What did he do?" makes sense together.
    if subject:
        return f"Subject: {subject}\n\n{clean_body}"
    return clean_body

if __name__ == '__main__':
    test = '''Hello Seven,
    
    What is the tallest mountain in the world?
    
    Kind regards
    Jeandre Greyling
    
    ________________________________
    From: sevenpotato9@gmail.com
    Sent: Thursday
    The swarm has consulted...
    '''
    result = strip_email_body(test)
    print('=== Stripped result ===')
    print(result)
    print('=== End ===')
def clean_subject(subject):
    # Strip swarm-generated subject prefixes so stored subjects stay clean
    prefixes = [
        '[Swarm] Unknown sender: ',
        '[Swarm] Received: ',
        '[Swarm] Full response: ',
        '[Swarm] Sender approved',
        '[Swarm] Sender ignored',
        '[Swarm] Sender added to notifications',
        'Re: [Swarm]',
        'Re: Re: ',
        'Re: ',
    ]
    cleaned = subject.strip()
    for prefix in prefixes:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
    return cleaned

def filter_non_english(text):
    # Simple heuristic - if more than 20% of chars are non-ASCII, translate
    if not text:
        return text
    non_ascii = sum(1 for c in text if ord(c) > 127)
    if non_ascii / max(len(text), 1) > 0.15:
        # Strip non-ASCII characters and note the filtering
        cleaned = ''.join(c if ord(c) < 128 else ' ' for c in text)
        # Collapse multiple spaces
        import re
        cleaned = re.sub(r' +', ' ', cleaned).strip()
        return cleaned
    return text

