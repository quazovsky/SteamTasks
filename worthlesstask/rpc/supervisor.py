"""Connection lifecycle: connect, hold, refresh, reconnect.

Owns one :class:`RpcClient` at a time and re-applies the presence after every
reconnect. "Discord is not running" is retryable, so the process can start before
Discord and attach when the client comes up.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from ..config.schema import AppConfig
from ..core.errors import (
    CLOSE_INVALID_CLIENT_ID,
    HandshakeError,
    IpcUnavailableError,
    ProtocolError,
    RpcError,
    RpcTimeout,
    worthlesstaskError,
    TransportError,
    is_fatal_close,
)
from ..core.logging import get_logger
from ..presence.builder import build_activity, diff_dropped
from .client import RpcClient

EXIT_OK = 0
EXIT_FATAL = 2
EXIT_ATTEMPTS_EXHAUSTED = 3

@dataclass
class SupervisorStats:
    started_at: float = field(default_factory=time.time)
    connections: int = 0
    connected: bool = False
    drops: int = 0
    updates: int = 0
    reconnects: int = 0
    errors: int = 0
    last_error: str | None = None
    last_connected_at: float | None = None
    last_dropped_at: float | None = None
    dropped_fields: dict[str, Any] = field(default_factory=dict)
    #: True once the presence has been cleared. A second clear costs a fresh IPC
    #: handshake and gets the client throttled for nothing.
    cleared: bool = False

    @property
    def uptime(self) -> float:
        return time.time() - self.started_at

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["uptime_s"] = round(self.uptime, 1)
        return data

class PresenceSupervisor:
    """Drives presence over a reconnecting IPC connection."""

    def __init__(
        self,
        config: AppConfig,
        logger: logging.Logger | None = None,
        client_factory: Callable[[], RpcClient] | None = None,
        clock: Callable[[], float] = time.time,
        identity_refresher: Callable[[], str] | None = None,
    ) -> None:
        self.config = config
        self.log = logger or get_logger()
        self._clock = clock
        self._client_factory = client_factory or self._default_client_factory
        self._identity_refresher = identity_refresher
        self.stats = SupervisorStats()
        #: Guards against an endless resolve-retry loop when the id keeps failing.
        self._identity_retried = False
        #: Set once, so the elapsed timer survives reconnects instead of resetting.
        self._presence_started_at = clock()

    def _default_client_factory(self) -> RpcClient:
        return RpcClient(
            client_id=self.config.client_id,
            logger=self.log,
            command_timeout=self.config.command_timeout,
            handshake_timeout=self.config.handshake_timeout,
        )

    # Presence
    def build(self) -> dict[str, Any]:
        return build_activity(
            game_name=self.config.game_name,
            activity_type=self.config.activity_type,
            details=self.config.details,
            state=self.config.state,
            started_at=self._presence_started_at if self.config.show_elapsed else None,
            large_image=self.config.large_image,
            large_text=self.config.large_text,
            small_image=self.config.small_image,
            small_text=self.config.small_text,
            buttons=self.config.buttons,
            party_size=self.config.party_size,
            party_id=self.config.party_id,
        )

    def apply(self, client: RpcClient) -> None:
        """Push the current presence and report anything Discord discarded."""
        activity = self.build()
        echoed = client.set_activity(activity)
        self.stats.updates += 1
        self.stats.connected = True
        self.stats.last_error = None
        dropped = diff_dropped(activity, echoed)
        if dropped:
            self.stats.dropped_fields = dropped
            self.log.warning(
                "Discord dropped or rewrote activity fields",
                extra={"dropped": dropped},
            )
        self.log.info(
            "presence set",
            extra={
                "game": activity.get("name"),
                "type": activity.get("type"),
                "application_id": self.config.client_id,
            },
        )

    # Identity self-healing
    def _try_refresh_identity(self, exc: HandshakeError) -> bool:
        """Re-derive the application id after Discord rejects it.

        Close code 4000 means "this application id is not a real application".
        Discord can re-issue a game's application, so the id stored in the config
        is re-derived from the game name once before giving up. Returns True when
        the caller should retry instead of stopping.
        """
        if exc.code != CLOSE_INVALID_CLIENT_ID:
            return False
        if self._identity_refresher is None:
            return False
        if self._identity_retried:
            self.log.error("the refreshed application id was rejected too")
            return False

        self._identity_retried = True
        previous = self.config.client_id
        try:
            fresh = self._identity_refresher()
        except worthlesstaskError as refresh_error:
            self.log.error(
                "could not refresh the application id",
                extra={"error": str(refresh_error)},
            )
            return False

        if not fresh or fresh == previous:
            self.log.error(
                "re-resolution returned the same rejected application id",
                extra={"application_id": previous},
            )
            return False

        self.config.client_id = fresh
        self.log.info(
            "application id re-resolved after rejection",
            extra={"previous": previous, "application_id": fresh},
        )
        return True

    # Main loop
    def run(self, stop_event: threading.Event) -> int:
        """Run until ``stop_event`` is set or the failure is unrecoverable."""
        attempt = 0
        if stop_event.is_set():
            # Asked to stop before starting: nothing was ever set, so there is
            # nothing to clear. Saying so stops the caller opening a connection
            # purely to clear an activity that does not exist.
            self.stats.cleared = True
        self.log.info(
            "supervisor starting",
            extra={
                "game": self.config.game_name,
                "application_id": self.config.client_id,
                "refresh_interval_s": self.config.refresh_interval,
            },
        )

        while not stop_event.is_set():
            attempt += 1
            client: RpcClient | None = None
            try:
                client = self._client_factory()
                client.connect()
                self.stats.connections += 1
                self.stats.last_connected_at = time.time()
                attempt = 0  # a successful handshake resets the backoff ladder
                self._identity_retried = False
                user = client.user or {}
                self.log.info(
                    "connected to Discord",
                    extra={"user": user.get("username"), "user_id": user.get("id")},
                )
                self.apply(client)
                self._hold(client, stop_event)

            except IpcUnavailableError as exc:
                self.stats.errors += 1
                self.stats.last_error = str(exc)
                self.log.warning(
                    "Discord IPC unavailable; will retry",
                    extra={"error": str(exc), "attempt": attempt},
                )
            except HandshakeError as exc:
                self.stats.errors += 1
                self.stats.last_error = str(exc)
                if is_fatal_close(exc.code):
                    if self._try_refresh_identity(exc):
                        continue
                    self.log.error(
                        "unrecoverable handshake rejection; stopping",
                        extra={"code": exc.code, "close_message": exc.message},
                    )
                    return EXIT_FATAL
                self.log.warning("handshake failed; will retry", extra={"error": str(exc)})
            except (TransportError, RpcTimeout, ProtocolError, OSError) as exc:
                # OSError covers the ordinary "Discord is not running" case: the pipe
                # or socket simply is not there. That is retryable like anything else,
                # and letting it escape would kill the process instead of waiting.
                self.stats.errors += 1
                self.stats.last_error = str(exc)
                self.log.warning("connection error; will retry", extra={"error": str(exc)})
            except RpcError as exc:
                self.stats.errors += 1
                self.stats.last_error = str(exc)
                self.log.error("Discord rejected a command", extra={"error": str(exc)})
            except KeyboardInterrupt:
                break
            finally:
                self.stats.connected = False
                if client is not None:
                    client.close(clear=stop_event.is_set() and self.config.clear_on_exit)
                    if client.cleared:
                        # Remembered here and in the client so the caller can see it
                        # whichever object it still holds, and clear only once.
                        self.stats.cleared = True
                        client.cleared = True

            if stop_event.is_set():
                break

            if not self.config.backoff.should_retry(attempt):
                self.log.error("reconnect attempts exhausted", extra={"attempts": attempt})
                return EXIT_ATTEMPTS_EXHAUSTED

            delay = self.config.backoff.delay_for(attempt)
            self.stats.reconnects += 1
            self.log.info(
                "reconnecting",
                extra={"attempt": attempt, "delay_s": round(delay, 2)},
            )
            if stop_event.wait(delay):
                break

        self.log.info("supervisor stopped", extra=self.stats.as_dict())
        return EXIT_OK

    def _hold(self, client: RpcClient, stop_event: threading.Event) -> None:
        """Keep the presence alive until the connection drops or we are asked to stop."""
        next_refresh = time.monotonic() + self.config.refresh_interval
        while not stop_event.is_set():
            if client.wait_closed(min(0.2, max(0, next_refresh - time.monotonic()))):
                self.stats.drops += 1
                self.stats.last_dropped_at = time.time()
                self.log.warning(
                    "connection lost",
                    extra={"code": client.close_code, "reason": client.close_reason},
                )
                return
            if stop_event.is_set():
                return
            if time.monotonic() < next_refresh:
                continue
            next_refresh = time.monotonic() + self.config.refresh_interval
            # Periodic refresh: re-assert the presence so it survives Discord
            # restarts, sleep/wake cycles and client-side activity timeouts.
            try:
                self.apply(client)
            except (TransportError, RpcTimeout, RpcError) as exc:
                self.stats.errors += 1
                self.stats.last_error = str(exc)
                self.log.warning("refresh failed; reconnecting", extra={"error": str(exc)})
                self.stats.drops += 1
                return
