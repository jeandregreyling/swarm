"""
utils/structured_logger.py — JSON structured logging (E.3.1)
═══════════════════════════════════════════════════════════════════════════════
Usage:
    from utils.structured_logger import setup_logging
    setup_logging()  # Call once at startup
"""

import json
import logging
import os
import sys
import uuid
from logging.handlers import RotatingFileHandler


class JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON."""

    def format(self, record):
        entry = {
            'timestamp': self.formatTime(record, self.datefmt),
            'level': record.levelname,
            'service': getattr(record, 'service', record.name),
            'message': record.getMessage(),
        }
        # Add correlation ID if present
        req_id = getattr(record, 'request_id', None)
        if req_id:
            entry['request_id'] = req_id
        # Add exception info
        if record.exc_info and record.exc_info[0]:
            entry['exception'] = self.formatException(record.exc_info)
        # Add extra metadata
        extra = getattr(record, 'extra_data', None)
        if extra:
            entry['meta'] = extra
        return json.dumps(entry, default=str)


def setup_logging(log_dir=None, level=None):
    """Configure structured JSON logging with rotation.
    Call once at process startup.
    """
    log_level = getattr(logging, (level or os.environ.get('SWARM_LOG_LEVEL', 'INFO')).upper(), logging.INFO)
    log_dir = log_dir or os.path.join(os.environ.get('SWARM_ROOT', '.'), 'logs')
    os.makedirs(log_dir, exist_ok=True)

    formatter = JSONFormatter()

    # File handler with rotation (10MB, 5 backups)
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, 'swarm.log'),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8',
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)

    # Also log to stderr for development
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(log_level)

    root = logging.getLogger()
    root.setLevel(log_level)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)


def get_request_id():
    """Get or create a correlation ID for the current request."""
    try:
        from flask import request, g
        if not hasattr(g, 'request_id'):
            g.request_id = request.headers.get('X-Request-ID', uuid.uuid4().hex[:12])
        return g.request_id
    except Exception:
        return uuid.uuid4().hex[:12]
