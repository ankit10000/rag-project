"""Backend settings (local, single-user). Only cheap imports here."""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

API_PREFIX = "/api/v1"
DEFAULT_HOST = "127.0.0.1"          # loopback only by default (Phase 7 owns wider exposure)
DEFAULT_PORT = 8765
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}

# Uploaded PDFs are written here (created on first upload, never elsewhere).
UPLOAD_DIR = os.path.join(ROOT, "data", "uploads")
MAX_FILENAME_LENGTH = 120

# Bounded listing sizes
MAX_HISTORY_MESSAGES = 200
MAX_MEMORIES_LISTED = 200
MAX_CONVERSATIONS_LISTED = 200
