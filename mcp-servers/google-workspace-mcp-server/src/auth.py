"""
Shared OAuth2 authentication for all Google Workspace APIs.
Single token with combined scopes — Calendar, Tasks, Gmail, Sheets.
"""

import os
import logging
import threading
import asyncio
from pathlib import Path

from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

# Combined scopes for all Google Workspace services
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/tasks',
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.settings.basic',
    'https://www.googleapis.com/auth/spreadsheets',
]

# Resolve paths relative to project root (parent of src/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOKEN_PATH = _PROJECT_ROOT / 'token.json'
CREDENTIALS_PATH = _PROJECT_ROOT / 'credentials.json'


class GoogleAuth:
    """Thread-safe Google OAuth2 credential manager with background refresh."""

    def __init__(self):
        self._creds: Credentials = None
        self._services: dict = {}  # Keyed by (api_name, api_version)
        self._lock = threading.Lock()
        self._healthy = True
        self._error_msg = None

    @property
    def healthy(self) -> bool:
        return self._healthy

    @property
    def error_msg(self) -> str:
        return self._error_msg

    def _refresh_token(self, creds: Credentials) -> Credentials:
        """Refresh the access token and persist to disk."""
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json())
        logger.info("Access token refreshed (expires: %s)", creds.expiry)
        return creds

    def _get_creds(self) -> Credentials:
        """Get valid credentials, refreshing if needed. Must be called under lock."""
        creds = self._creds

        # Load from disk if not cached
        if creds is None and TOKEN_PATH.exists():
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

        if not creds:
            self._healthy = False
            self._error_msg = (
                f"No token.json found at {TOKEN_PATH}. "
                "Run 'python src/auth.py' to set up authentication."
            )
            raise RuntimeError(self._error_msg)

        # Refresh if expired
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                try:
                    creds = self._refresh_token(creds)
                except RefreshError as e:
                    self._healthy = False
                    self._error_msg = (
                        f"Refresh token invalid/revoked ({e}). "
                        "Run 'python src/auth.py' to re-authenticate."
                    )
                    raise RuntimeError(self._error_msg) from e
            else:
                self._healthy = False
                self._error_msg = "Credentials invalid and no refresh token. Run 'python src/auth.py'."
                raise RuntimeError(self._error_msg)

        self._healthy = True
        self._error_msg = None
        self._creds = creds
        return creds

    def get_service(self, api_name: str, api_version: str):
        """
        Get an authenticated Google API service client.
        Caches service objects per (api_name, version) and handles token refresh.
        """
        key = (api_name, api_version)

        with self._lock:
            # Fast path: cached service with valid creds
            if key in self._services and self._creds and self._creds.valid:
                return self._services[key]

            creds = self._get_creds()
            service = build(api_name, api_version, credentials=creds)
            self._services[key] = service
            return service

    def invalidate_services(self):
        """Force all cached services to be rebuilt on next access."""
        with self._lock:
            self._services.clear()

    async def background_refresh_loop(self, interval_minutes: int = 45):
        """Proactively refresh token to prevent expiry during use."""
        while True:
            await asyncio.sleep(interval_minutes * 60)
            with self._lock:
                if self._creds and self._creds.refresh_token:
                    try:
                        self._creds = self._refresh_token(self._creds)
                        self._services.clear()  # Rebuild with new creds
                        self._healthy = True
                        self._error_msg = None
                        logger.info("Background token refresh succeeded")
                    except RefreshError as e:
                        self._healthy = False
                        self._error_msg = f"Background refresh failed: {e}"
                        logger.error("Background token refresh failed: %s", e)
                    except Exception as e:
                        logger.error("Unexpected error in background refresh: %s", e)


# Singleton instance
auth = GoogleAuth()


# === Convenience accessors for each service ===

def get_calendar_service():
    return auth.get_service('calendar', 'v3')

def get_tasks_service():
    return auth.get_service('tasks', 'v1')

def get_gmail_service():
    return auth.get_service('gmail', 'v1')

def get_sheets_service():
    return auth.get_service('sheets', 'v4')


# === Standalone auth script ===

def authenticate():
    """Interactive OAuth2 flow — run once to create token.json."""
    print(f"Credentials path: {CREDENTIALS_PATH}")
    print(f"Token path: {TOKEN_PATH}")
    print(f"Scopes: {len(SCOPES)} APIs (Calendar, Tasks, Gmail, Sheets)")
    print()

    if not CREDENTIALS_PATH.exists():
        raise FileNotFoundError(
            f"credentials.json not found at {CREDENTIALS_PATH}. "
            "Download it from Google Cloud Console."
        )

    flow = InstalledAppFlow.from_client_secrets_file(
        str(CREDENTIALS_PATH),
        SCOPES,
        redirect_uri='urn:ietf:wg:oauth:2.0:oob'
    )
    creds = flow.run_local_server(port=0, access_type='offline', prompt='consent')
    TOKEN_PATH.write_text(creds.to_json())

    print()
    print("Authentication successful! token.json created.")
    print("You can now run the server with: python src/server.py")


if __name__ == '__main__':
    authenticate()
