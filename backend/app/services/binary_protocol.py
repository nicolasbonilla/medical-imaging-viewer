"""
Binary Protocol Implementation for Medical Image Transfer.

Implements efficient binary serialization/deserialization for medical images
to achieve 17-42x speedup over Base64 encoding (PoC validated).

Protocol Specification: See BINARY_PROTOCOL_SPEC.md
"""

import struct
import zlib
from enum import IntEnum
from typing import Optional, Dict, Any, Tuple
import numpy as np

from app.core.logging import get_logger
from app.core.config import get_settings

logger = get_logger(__name__)
settings = get_settings()


class MessageType(IntEnum):
    """Binary protocol message types."""
    SLICE_DATA = 0x01      # Medical image slice data
    METADATA = 0x02        # Image metadata
    ERROR = 0x03           # Error message
    HEARTBEAT = 0x04       # Connection heartbeat
    ACK = 0x05             # Acknowledgment


class CompressionType(IntEnum):
    """Compression algorithms."""
    NONE = 0x00           # No compression
    ZLIB = 0x01           # zlib compression
    LZ4 = 0x02            # LZ4 compression (fastest)
    ZSTD = 0x03           # Zstandard (best ratio)


# NumPy dtype to binary protocol mapping
DTYPE_TO_CODE = {
    np.dtype('uint8'):   0x01,
    np.dtype('uint16'):  0x02,
    np.dtype('int16'):   0x03,
    np.dtype('float32'): 0x04,
    np.dtype('float64'): 0x05,
}

CODE_TO_DTYPE = {v: k for k, v in DTYPE_TO_CODE.items()}

DTYPE_SIZES = {
    0x01: 1,  # uint8
    0x02: 2,  # uint16
    0x03: 2,  # int16
    0x04: 4,  # float32
    0x05: 8,  # float64
}


class BinaryProtocolHeader:
    """
    Binary protocol message header (24 bytes).

    Format:
        magic (4 bytes): 0x4D4449 ("MDI" - Medical Digital Imaging)
        version (2 bytes): Protocol version (1)
        message_type (1 byte): MessageType enum
        compression (1 byte): CompressionType enum
        payload_length (4 bytes): Payload size in bytes
        sequence_num (4 bytes): Sequence number
        crc32 (4 bytes): Payload CRC32 checksum
        reserved (4 bytes): Reserved for future use
    """

    MAGIC = 0x4D4449  # "MDI"
    VERSION = 1
    SIZE = 24  # Header size in bytes

    # Struct format: Little-endian
    # I = uint32, H = uint16, B = uint8
    FORMAT = '<IHBBI I I I'  # 4+2+1+1+4+4+4+4 = 24 bytes

    def __init__(
        self,
        message_type: MessageType,
        payload_length: int,
        sequence_num: int = 0,
        crc32: int = 0,
        compression: CompressionType = CompressionType.NONE
    ):
        self.magic = self.MAGIC
        self.version = self.VERSION
        self.message_type = message_type
        self.compression = compression
        self.payload_length = payload_length
        self.sequence_num = sequence_num
        self.crc32 = crc32
        self.reserved = 0

    def pack(self) -> bytes:
        """Pack header into 24 bytes."""
        return struct.pack(
            self.FORMAT,
            self.magic,
            self.version,
            self.message_type,
            self.compression,
            self.payload_length,
            self.sequence_num,
            self.crc32,
            self.reserved
        )

    @classmethod
    def unpack(cls, data: bytes) -> 'BinaryProtocolHeader':
        """Unpack 24 bytes into header."""
        if len(data) < cls.SIZE:
            raise ValueError(f"Invalid header size: {len(data)} < {cls.SIZE}")

        magic, version, msg_type, compression, payload_len, seq_num, crc, reserved = \
            struct.unpack(cls.FORMAT, data[:cls.SIZE])

        if magic != cls.MAGIC:
            raise ValueError(f"Invalid magic number: 0x{magic:X}")

        if version != cls.VERSION:
            raise ValueError(f"Unsupported protocol version: {version}")

        return cls(
            message_type=MessageType(msg_type),
            payload_length=payload_len,
            sequence_num=seq_num,
            crc32=crc,
            compression=CompressionType(compression)
        )


class BinarySerializer:
    """
    Binary protocol serializer for medical images.

    Serializes NumPy arrays and metadata into efficient binary format,
    achieving 17-42x speedup over Base64 (PoC validated).
    """

    def __init__(self, compression: CompressionType = CompressionType.NONE):
        """
        Initialize binary serializer.

        Args:
            compression: Compression type to use
        """
        self.compression = compression
        self.sequence_num = 0

        logger.info(
            "BinarySerializer initialized",
            extra={"compression": compression.name}
        )

    def serialize_slice(
        self,
        slice_data: np.ndarray,
        file_id: str,
        slice_index: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bytes:
        """
        Serialize a medical image slice to binary format.

        Args:
            slice_data: NumPy array with pixel data (2D)
            file_id: Unique file identifier
            slice_index: Slice index in volume
            metadata: Optional metadata dict with window/level, min/max, etc.

        Returns:
            Complete binary message (header + payload)

        Raises:
            ValueError: If input data is invalid
        """
        if slice_data.ndim != 2:
            raise ValueError(f"Expected 2D array, got {slice_data.ndim}D")

        if len(file_id) > 32:
            raise ValueError(f"file_id too long: {len(file_id)} > 32")

        # Get metadata
        meta = metadata or {}
        window_center = meta.get('window_center', 0.0)
        window_width = meta.get('window_width', 0.0)
        min_value = meta.get('min_value', float(np.min(slice_data)))
        max_value = meta.get('max_value', float(np.max(slice_data)))

        # Ensure contiguous C-order array
        if not slice_data.flags['C_CONTIGUOUS']:
            slice_data = np.ascontiguousarray(slice_data)

        # Get dtype code
        dtype_code = DTYPE_TO_CODE.get(slice_data.dtype)
        if dtype_code is None:
            raise ValueError(f"Unsupported dtype: {slice_data.dtype}")

        # Build metadata header (68 bytes)
        height, width = slice_data.shape

        # file_id: 32 bytes (padded with zeros)
        file_id_bytes = file_id.encode('utf-8')[:32].ljust(32, b'\x00')

        # Metadata header format:
        # 32s = file_id (32 bytes)
        # I = slice_index (uint32)
        # I = width (uint32)
        # I = height (uint32)
        # I = dtype (uint32)
        # f = min_value (float32)
        # f = max_value (float32)
        # f = window_center (float32)
        # f = window_width (float32)
        # I = reserved (uint32)
        metadata_header = struct.pack(
            '<32s I I I I f f f f I',
            file_id_bytes,
            slice_index,
            width,
            height,
            dtype_code,
            min_value,
            max_value,
            window_center,
            window_width,
            0  # reserved
        )

        # Get raw pixel data
        pixel_data = slice_data.tobytes()

        # Build payload
        payload = metadata_header + pixel_data

        # Apply compression if enabled
        if self.compression == CompressionType.ZLIB:
            payload = zlib.compress(payload, level=6)
        elif self.compression == CompressionType.LZ4:
            try:
                import lz4.frame
                payload = lz4.frame.compress(payload)
            except ImportError:
                logger.warning("LZ4 not available, falling back to no compression")
                self.compression = CompressionType.NONE
        elif self.compression == CompressionType.ZSTD:
            try:
                import zstandard as zstd
                cctx = zstd.ZstdCompressor()
                payload = cctx.compress(payload)
            except ImportError:
                logger.warning("ZSTD not available, falling back to no compression")
                self.compression = CompressionType.NONE

        # Calculate CRC32
        crc = zlib.crc32(payload) & 0xffffffff

        # Create header
        header = BinaryProtocolHeader(
            message_type=MessageType.SLICE_DATA,
            payload_length=len(payload),
            sequence_num=self.sequence_num,
            crc32=crc,
            compression=self.compression
        )

        self.sequence_num += 1

        # Pack message
        message = header.pack() + payload

        logger.debug(
            "Serialized slice to binary",
            extra={
                "file_id": file_id,
                "slice_index": slice_index,
                "shape": slice_data.shape,
                "dtype": slice_data.dtype.name,
                "payload_size": len(payload),
                "total_size": len(message),
                "compression": self.compression.name,
                "sequence": self.sequence_num - 1
            }
        )

        return message

    def serialize_metadata(
        self,
        metadata: Dict[str, Any],
        file_id: str
    ) -> bytes:
        """
        Serialize image metadata to binary format.

        Args:
            metadata: Metadata dictionary
            file_id: File identifier

        Returns:
            Binary message with metadata
        """
        import json

        # Convert metadata to JSON
        metadata_json = json.dumps(metadata).encode('utf-8')

        # Calculate CRC32
        crc = zlib.crc32(metadata_json) & 0xffffffff

        # Create header
        header = BinaryProtocolHeader(
            message_type=MessageType.METADATA,
            payload_length=len(metadata_json),
            sequence_num=self.sequence_num,
            crc32=crc,
            compression=CompressionType.NONE  # Metadata not compressed
        )

        self.sequence_num += 1

        message = header.pack() + metadata_json

        logger.debug(
            "Serialized metadata",
            extra={
                "file_id": file_id,
                "payload_size": len(metadata_json),
                "total_size": len(message)
            }
        )

        return message

    def serialize_error(
        self,
        error_code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ) -> bytes:
        """
        Serialize error message.

        Args:
            error_code: Error code
            message: Error message
            details: Optional error details

        Returns:
            Binary error message
        """
        import json

        error_dict = {
            "code": error_code,
            "message": message,
            "details": details or {}
        }

        error_json = json.dumps(error_dict).encode('utf-8')

        crc = zlib.crc32(error_json) & 0xffffffff

        header = BinaryProtocolHeader(
            message_type=MessageType.ERROR,
            payload_length=len(error_json),
            sequence_num=self.sequence_num,
            crc32=crc,
            compression=CompressionType.NONE
        )

        self.sequence_num += 1

        return header.pack() + error_json

    def serialize_heartbeat(self, server_load: float = 0.0) -> bytes:
        """
        Serialize heartbeat message.

        Args:
            server_load: Server load 0.0-1.0

        Returns:
            Binary heartbeat message
        """
        import time

        # Heartbeat payload: timestamp (uint64) + server_load (float32)
        timestamp_ms = int(time.time() * 1000)
        payload = struct.pack('<Q f', timestamp_ms, server_load)

        crc = zlib.crc32(payload) & 0xffffffff

        header = BinaryProtocolHeader(
            message_type=MessageType.HEARTBEAT,
            payload_length=len(payload),
            sequence_num=self.sequence_num,
            crc32=crc,
            compression=CompressionType.NONE
        )

        self.sequence_num += 1

        return header.pack() + payload


class BinaryDeserializer:
    """
    Binary protocol deserializer for medical images.

    Deserializes binary messages back into NumPy arrays and metadata.
    """

    def __init__(self):
        """Initialize binary deserializer."""
        logger.info("BinaryDeserializer initialized")

    def deserialize(self, data: bytes) -> Tuple[BinaryProtocolHeader, Any]:
        """
        Deserialize binary message.

        Args:
            data: Complete binary message (header + payload)

        Returns:
            Tuple of (header, payload_data)

        Raises:
            ValueError: If message is invalid or corrupted
        """
        if len(data) < BinaryProtocolHeader.SIZE:
            raise ValueError(f"Message too short: {len(data)} bytes")

        # Parse header
        header = BinaryProtocolHeader.unpack(data[:BinaryProtocolHeader.SIZE])

        # Extract payload
        payload_start = BinaryProtocolHeader.SIZE
        payload_end = payload_start + header.payload_length

        if len(data) < payload_end:
            raise ValueError(
                f"Incomplete message: expected {payload_end} bytes, got {len(data)}"
            )

        payload = data[payload_start:payload_end]

        # Verify CRC32
        calculated_crc = zlib.crc32(payload) & 0xffffffff
        if calculated_crc != header.crc32:
            raise ValueError(
                f"CRC mismatch: expected 0x{header.crc32:08X}, "
                f"got 0x{calculated_crc:08X}"
            )

        # Decompress if needed
        if header.compression == CompressionType.ZLIB:
            payload = zlib.decompress(payload)
        elif header.compression == CompressionType.LZ4:
            import lz4.frame
            payload = lz4.frame.decompress(payload)
        elif header.compression == CompressionType.ZSTD:
            import zstandard as zstd
            dctx = zstd.ZstdDecompressor()
            payload = dctx.decompress(payload)

        # Deserialize based on message type
        if header.message_type == MessageType.SLICE_DATA:
            return header, self._deserialize_slice(payload)
        elif header.message_type == MessageType.METADATA:
            return header, self._deserialize_metadata(payload)
        elif header.message_type == MessageType.ERROR:
            return header, self._deserialize_error(payload)
        elif header.message_type == MessageType.HEARTBEAT:
            return header, self._deserialize_heartbeat(payload)
        else:
            raise ValueError(f"Unknown message type: {header.message_type}")

    def _deserialize_slice(self, payload: bytes) -> Dict[str, Any]:
        """Deserialize SLICE_DATA payload."""
        if len(payload) < 68:
            raise ValueError(f"Slice payload too short: {len(payload)} bytes")

        # Parse metadata header (68 bytes)
        file_id_bytes, slice_index, width, height, dtype_code, \
            min_value, max_value, window_center, window_width, reserved = \
            struct.unpack('<32s I I I I f f f f I', payload[:68])

        file_id = file_id_bytes.rstrip(b'\x00').decode('utf-8')

        # Get dtype
        dtype = CODE_TO_DTYPE.get(dtype_code)
        if dtype is None:
            raise ValueError(f"Unknown dtype code: {dtype_code}")

        # Calculate expected pixel data size
        expected_size = width * height * DTYPE_SIZES[dtype_code]
        pixel_data = payload[68:]

        if len(pixel_data) != expected_size:
            raise ValueError(
                f"Invalid pixel data size: expected {expected_size}, "
                f"got {len(pixel_data)}"
            )

        # Reconstruct NumPy array
        slice_array = np.frombuffer(pixel_data, dtype=dtype).reshape((height, width))

        return {
            "file_id": file_id,
            "slice_index": slice_index,
            "width": width,
            "height": height,
            "dtype": dtype.name,
            "min_value": min_value,
            "max_value": max_value,
            "window_center": window_center,
            "window_width": window_width,
            "data": slice_array
        }

    def _deserialize_metadata(self, payload: bytes) -> Dict[str, Any]:
        """Deserialize METADATA payload."""
        import json
        return json.loads(payload.decode('utf-8'))

    def _deserialize_error(self, payload: bytes) -> Dict[str, Any]:
        """Deserialize ERROR payload."""
        import json
        return json.loads(payload.decode('utf-8'))

    def _deserialize_heartbeat(self, payload: bytes) -> Dict[str, Any]:
        """Deserialize HEARTBEAT payload."""
        timestamp_ms, server_load = struct.unpack('<Q f', payload)
        return {
            "timestamp": timestamp_ms,
            "server_load": server_load
        }
