"""
channels/base.py — shared boilerplate for all OmegaClaw communication channels.

Every channel subclass must implement:
  - _run_loop()     connection / polling logic; runs in a daemon thread
  - send_message()  deliver a text message to the channel
"""

import abc
import os
import threading


class BaseChannel(abc.ABC):
    def __init__(self):
        # inbound message queue (single-slot, newest wins via concatenation)
        self._last_message = ""
        self._msg_lock = threading.Lock()

        # auth state
        self._auth_secret = ""
        self._authenticated_id = None
        self._auth_lock = threading.Lock()

        # lifecycle
        self._running = False
        self._connected = False
        self._thread = None

    # ------------------------------------------------------------------
    # Message queue
    # ------------------------------------------------------------------

    def _set_last(self, msg: str) -> None:
        with self._msg_lock:
            if self._last_message == "":
                self._last_message = msg
            else:
                self._last_message = self._last_message + " | " + msg

    def getLastMessage(self) -> str:
        with self._msg_lock:
            tmp = self._last_message
            self._last_message = ""
            return tmp

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _set_auth_secret(self, secret=None) -> None:
        if secret is None:
            secret = os.environ.get("OMEGACLAW_AUTH_SECRET", "")
        with self._auth_lock:
            self._auth_secret = (secret or "").strip()
            self._authenticated_id = None

    @staticmethod
    def _parse_auth_candidate(msg: str) -> str:
        text = msg.strip()
        lower = text.lower()
        if lower.startswith("auth "):
            return text[5:].strip()
        if lower.startswith("/auth "):
            return text[6:].strip()
        return text

    def _is_allowed_message(self, sender_id: str, msg: str) -> str:
        """
        Returns one of: 'allow' | 'auth_bound' | 'ignore'

        Subclasses may override this when auth requires more than one
        identity field (e.g. Telegram needs user_id + chat_id).
        """
        candidate = self._parse_auth_candidate(msg)
        with self._auth_lock:
            if not self._auth_secret:
                return "allow"
            if candidate == self._auth_secret:
                if self._authenticated_id is None:
                    self._authenticated_id = sender_id
                    return "auth_bound"
                return "ignore"
            if self._authenticated_id is None:
                return "ignore"
            return "allow" if sender_id == self._authenticated_id else "ignore"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, auth_secret=None) -> threading.Thread:
        self._set_auth_secret(auth_secret)
        self._running = True
        self._connected = False
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        return self._thread

    def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def _run_loop(self) -> None:
        """Channel-specific connection / polling logic."""

    @abc.abstractmethod
    def send_message(self, text: str) -> None:
        """Send text to the channel."""
