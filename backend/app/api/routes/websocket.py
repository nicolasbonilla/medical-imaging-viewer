"""
WebSocket API Routes.

Provides WebSocket endpoints for real-time medical image streaming
with binary protocol support.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, status
from typing import Optional
import uuid

from app.core.logging import get_logger
from app.core.container import get_imaging_service
from app.security.auth import get_current_active_user
from app.security.jwt_manager import TokenData, get_token_manager
from app.services.websocket_service import WebSocketService, ConnectionManager
from app.services.binary_protocol import CompressionType

logger = get_logger(__name__)
router = APIRouter(prefix="/ws", tags=["websocket"])

# Global connection manager (shared across all connections)
connection_manager = ConnectionManager()

# WebSocket close code 1008 — "Policy Violation" (RFC 6455 §7.4.1). Used for
# every authentication failure so that clients cannot distinguish "no token"
# from "bad token" from "expired token".
WS_POLICY_VIOLATION = status.WS_1008_POLICY_VIOLATION


# ─────────────────────────────────────────────────────────────────────────────
# RC-017 — risk control for HAZ-010 (unauthorized access to patient imaging, S4)
#
# CAPA-001 §2.2: the Risk Management File recorded RC-017 as "VERIFIED — All 103
# API endpoints require JWT authentication (100% coverage)". This module was not
# authenticated in any form. The REST surface is protected; the WebSocket
# transport was not, and it streams pixel data by file_id.
#
# Verified by: backend/tests/unit/test_rc017_websocket_auth.py
#              (tests named test_rc017_*). Removing this control MUST turn CI red.
# ─────────────────────────────────────────────────────────────────────────────
def _extract_token(websocket: WebSocket) -> Optional[str]:
    """Extract a bearer token from a WebSocket handshake.

    Three transports are accepted, in order of preference:

    1. ``Authorization: Bearer <token>`` header — for non-browser clients.
    2. ``Sec-WebSocket-Protocol: bearer, <token>`` — the only way a browser can
       supply a credential without putting it in the URL.
    3. ``?token=<token>`` query parameter — accepted for compatibility only.

    Option 3 is deliberately last: query strings are recorded in proxy logs,
    load-balancer access logs and browser history, so a token supplied that way
    should be treated as disclosed. Its use is logged as a warning.
    """
    header = websocket.headers.get("authorization")
    if header and header.lower().startswith("bearer "):
        return header[7:].strip() or None

    protocols = websocket.headers.get("sec-websocket-protocol")
    if protocols:
        parts = [p.strip() for p in protocols.split(",")]
        if len(parts) >= 2 and parts[0].lower() == "bearer":
            return parts[1] or None

    token = websocket.query_params.get("token")
    if token:
        logger.warning(
            "WebSocket token supplied via query string — credentials in URLs are "
            "recorded by proxies and access logs. Use the Authorization header or "
            "the 'bearer' subprotocol.",
        )
        return token

    return None


async def _authenticate_websocket(websocket: WebSocket) -> Optional[TokenData]:
    """Authenticate a WebSocket handshake, or close it with 1008.

    Returns the decoded token data on success, ``None`` after having closed the
    connection on failure. Fails closed: any error path closes the socket.

    The token is never logged, and the close reason never reveals *why*
    authentication failed.
    """
    token = _extract_token(websocket)

    if not token:
        logger.warning(
            "WebSocket connection rejected: no credentials presented",
            extra={"client": websocket.client.host if websocket.client else "unknown"},
        )
        await websocket.close(code=WS_POLICY_VIOLATION, reason="Authentication required")
        return None

    try:
        token_data = get_token_manager().decode_token_data(token)
    except Exception as exc:
        # Deliberately broad: an invalid, expired, malformed or unverifiable
        # token must all produce the same outcome for the caller.
        logger.warning(
            "WebSocket connection rejected: invalid credentials",
            extra={
                "error_type": type(exc).__name__,
                "client": websocket.client.host if websocket.client else "unknown",
            },
        )
        await websocket.close(code=WS_POLICY_VIOLATION, reason="Authentication required")
        return None

    logger.info(
        "WebSocket authenticated",
        extra={"user_id": token_data.user_id, "username": token_data.username},
    )
    return token_data


@router.websocket("/imaging")
async def websocket_imaging_endpoint(
    websocket: WebSocket,
    compression: Optional[str] = None,
    imaging_service=Depends(get_imaging_service),
):
    """
    WebSocket endpoint for real-time medical image streaming.

    Supports binary protocol for efficient data transfer with optional compression.

    Query Parameters:
        compression (optional): Compression type (none, zlib, lz4, zstd)

    Message Protocol (Client -> Server, JSON):
        - ping: {"type": "ping"}
        - request_slice: {"type": "request_slice", "file_id": "...", "slice_index": 0}
        - request_metadata: {"type": "request_metadata", "file_id": "..."}

    Message Protocol (Server -> Client, Binary):
        - SLICE_DATA: Binary protocol with pixel data
        - METADATA: Binary protocol with JSON metadata
        - ERROR: Binary protocol with error details
        - HEARTBEAT: Binary protocol with timestamp

    Example Usage (JavaScript):
        const ws = new WebSocket('ws://localhost:8000/ws/imaging?compression=none');

        ws.onmessage = (event) => {
            const arrayBuffer = await event.data.arrayBuffer();
            const deserializer = new BinaryDeserializer();
            const {header, payload} = deserializer.deserialize(arrayBuffer);

            if (header.messageType === MessageType.SLICE_DATA) {
                // Render slice data
                renderSlice(payload.data, payload.width, payload.height);
            }
        };

        // Request a slice
        ws.send(JSON.stringify({
            type: 'request_slice',
            file_id: 'abc123',
            slice_index: 42
        }));

    Authentication (RC-017):
        Required. Supply a bearer token via the Authorization header, the
        'bearer' WebSocket subprotocol, or (discouraged) a ?token= parameter.
        Unauthenticated connections are closed with code 1008.
    """
    # RC-017: authenticate BEFORE accepting the socket or constructing any
    # service that can read patient data. Fails closed.
    token_data = await _authenticate_websocket(websocket)
    if token_data is None:
        return

    # Parse compression type
    compression_type = CompressionType.NONE

    if compression:
        compression_lower = compression.lower()
        if compression_lower == "zlib":
            compression_type = CompressionType.ZLIB
        elif compression_lower == "lz4":
            compression_type = CompressionType.LZ4
        elif compression_lower == "zstd":
            compression_type = CompressionType.ZSTD

    # Generate unique connection ID
    connection_id = str(uuid.uuid4())

    # Create WebSocket service
    ws_service = WebSocketService(
        imaging_service=imaging_service,
        connection_manager=connection_manager,
        compression=compression_type,
    )

    logger.info(
        "WebSocket connection initiated",
        extra={
            "connection_id": connection_id,
            "compression": compression_type.name,
        },
    )

    # Handle connection lifecycle
    await ws_service.handle_connection(websocket, connection_id)


@router.get("/stats")
async def get_websocket_stats(current_user=Depends(get_current_active_user)):
    """
    Get WebSocket connection manager statistics.

    RC-017: authenticated. Operational telemetry about who is streaming what is
    not public information.

    Returns:
        Connection statistics including active connections, total messages sent, etc.

    Example Response:
        {
            "active_connections": 5,
            "total_messages_sent": 12345,
            "total_bytes_sent": 524288000,
            "average_bytes_per_message": 42500
        }
    """
    return connection_manager.get_stats()


@router.get("/connections/{connection_id}")
async def get_connection_stats(
    connection_id: str,
    current_user=Depends(get_current_active_user),
):
    """
    Get statistics for a specific connection.

    RC-017: authenticated.

    Args:
        connection_id: Connection identifier

    Returns:
        Connection statistics or 404 if not found

    Example Response:
        {
            "connection_id": "abc-123",
            "connected_at": "2025-11-22T14:00:00",
            "duration_seconds": 120.5,
            "messages_sent": 42,
            "bytes_sent": 1048576,
            "last_heartbeat": "2025-11-22T14:02:00",
            "heartbeat_age_seconds": 5.2
        }
    """
    stats = connection_manager.get_connection_stats(connection_id)

    if stats is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connection {connection_id} not found",
        )

    return stats
