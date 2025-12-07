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
from app.services.websocket_service import WebSocketService, ConnectionManager
from app.services.binary_protocol import CompressionType

logger = get_logger(__name__)
router = APIRouter(prefix="/ws", tags=["websocket"])

# Global connection manager (shared across all connections)
connection_manager = ConnectionManager()


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
    """
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
async def get_websocket_stats():
    """
    Get WebSocket connection manager statistics.

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
async def get_connection_stats(connection_id: str):
    """
    Get statistics for a specific connection.

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
