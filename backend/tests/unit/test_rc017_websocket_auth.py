"""RC-017 — authentication on the WebSocket imaging transport.

Risk control for HAZ-010 (unauthorized access to patient imaging, severity S4).
Raised by CAPA-001 §2.2, which found RC-017 recorded as "VERIFIED — All 103 API
endpoints require JWT authentication (100% coverage)" while
`app/api/routes/websocket.py` had no token parameter, no auth dependency and no
handshake authentication. The endpoint streams pixel data by file_id.

These tests use a WebSocket double rather than a live server so that the control
is verified without requiring Redis, GCS or the DI container — a risk-control
test that cannot run in CI is not a risk control.

Negative control (CAPA-001 §5): remove the `_authenticate_websocket` call from
the endpoint, or make it return a token unconditionally, and these tests MUST
fail.
"""
import pytest
from unittest.mock import MagicMock, patch

from app.api.routes.websocket import (
    WS_POLICY_VIOLATION,
    _authenticate_websocket,
    _extract_token,
)


class FakeClient:
    host = "203.0.113.9"


class FakeWebSocket:
    """Minimal stand-in for starlette's WebSocket during the handshake."""

    def __init__(self, headers=None, query_params=None):
        self.headers = headers or {}
        self.query_params = query_params or {}
        self.client = FakeClient()
        self.closed_with = None
        self.close_reason = None
        self.accepted = False

    async def close(self, code=1000, reason=None):
        self.closed_with = code
        self.close_reason = reason

    async def accept(self, *args, **kwargs):
        self.accepted = True


class TestRC017TokenExtraction:
    """The control must accept credentials over transports a real client can use."""

    def test_rc017_reads_authorization_header(self):
        ws = FakeWebSocket(headers={"authorization": "Bearer abc.def.ghi"})
        assert _extract_token(ws) == "abc.def.ghi"

    def test_rc017_authorization_header_is_case_insensitive(self):
        ws = FakeWebSocket(headers={"authorization": "bearer abc.def.ghi"})
        assert _extract_token(ws) == "abc.def.ghi"

    def test_rc017_reads_bearer_subprotocol(self):
        """The only way a browser can send a credential without putting it in the URL."""
        ws = FakeWebSocket(headers={"sec-websocket-protocol": "bearer, abc.def.ghi"})
        assert _extract_token(ws) == "abc.def.ghi"

    def test_rc017_reads_query_parameter(self):
        ws = FakeWebSocket(query_params={"token": "abc.def.ghi"})
        assert _extract_token(ws) == "abc.def.ghi"

    def test_rc017_no_credentials_yields_none(self):
        assert _extract_token(FakeWebSocket()) is None

    def test_rc017_empty_bearer_header_yields_none(self):
        """'Bearer ' with nothing after it must not be read as a valid token."""
        assert _extract_token(FakeWebSocket(headers={"authorization": "Bearer "})) is None

    def test_rc017_non_bearer_scheme_is_ignored(self):
        ws = FakeWebSocket(headers={"authorization": "Basic dXNlcjpwYXNz"})
        assert _extract_token(ws) is None

    def test_rc017_unrelated_subprotocol_is_not_read_as_a_token(self):
        ws = FakeWebSocket(headers={"sec-websocket-protocol": "graphql-ws"})
        assert _extract_token(ws) is None


@pytest.mark.asyncio
class TestRC017HandshakeIsRejected:
    """The core assertion of RC-017: no credential, no connection."""

    async def test_rc017_unauthenticated_connection_is_closed_1008(self):
        ws = FakeWebSocket()
        result = await _authenticate_websocket(ws)

        assert result is None, "unauthenticated handshake must not yield token data"
        assert ws.closed_with == WS_POLICY_VIOLATION == 1008
        assert not ws.accepted, "socket must never be accepted without credentials"

    async def test_rc017_invalid_token_is_closed_1008(self):
        ws = FakeWebSocket(headers={"authorization": "Bearer not-a-real-token"})

        with patch("app.api.routes.websocket.get_token_manager") as mgr:
            mgr.return_value.decode_token_data.side_effect = ValueError("bad signature")
            result = await _authenticate_websocket(ws)

        assert result is None
        assert ws.closed_with == 1008
        assert not ws.accepted

    async def test_rc017_expired_token_is_closed_1008(self):
        ws = FakeWebSocket(headers={"authorization": "Bearer expired"})

        with patch("app.api.routes.websocket.get_token_manager") as mgr:
            mgr.return_value.decode_token_data.side_effect = Exception("token expired")
            result = await _authenticate_websocket(ws)

        assert result is None
        assert ws.closed_with == 1008

    async def test_rc017_close_reason_does_not_disclose_the_failure_mode(self):
        """A caller must not be able to distinguish 'no token' from 'bad token'."""
        no_token = FakeWebSocket()
        await _authenticate_websocket(no_token)

        bad_token = FakeWebSocket(headers={"authorization": "Bearer nope"})
        with patch("app.api.routes.websocket.get_token_manager") as mgr:
            mgr.return_value.decode_token_data.side_effect = ValueError("bad signature")
            await _authenticate_websocket(bad_token)

        assert no_token.closed_with == bad_token.closed_with
        assert no_token.close_reason == bad_token.close_reason

    async def test_rc017_valid_token_is_admitted(self):
        ws = FakeWebSocket(headers={"authorization": "Bearer good"})
        token_data = MagicMock(user_id="u-1", username="clinician")

        with patch("app.api.routes.websocket.get_token_manager") as mgr:
            mgr.return_value.decode_token_data.return_value = token_data
            result = await _authenticate_websocket(ws)

        assert result is token_data
        assert ws.closed_with is None, "a valid credential must not be rejected"


@pytest.mark.asyncio
class TestRC017EndpointEnforcesAuth:
    """Guard the wiring, not just the helper: the endpoint must call the control
    and must abandon the connection when it fails."""

    async def test_rc017_endpoint_aborts_before_touching_imaging_data(self):
        from app.api.routes import websocket as ws_module

        ws = FakeWebSocket()
        imaging_service = MagicMock()

        with patch.object(ws_module, "WebSocketService") as ws_service_cls:
            await ws_module.websocket_imaging_endpoint(
                websocket=ws,
                compression=None,
                imaging_service=imaging_service,
            )

        assert ws.closed_with == 1008
        assert not ws.accepted
        ws_service_cls.assert_not_called(), (
            "no service capable of reading patient data may be constructed for an "
            "unauthenticated connection"
        )
        imaging_service.assert_not_called()
