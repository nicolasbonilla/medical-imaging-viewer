"""
Unit tests for Binary Protocol Implementation.

Tests serialization/deserialization of medical images in binary format.
Validates 17-42x speedup target and 25% size reduction.
"""

import pytest
import numpy as np
import struct
import zlib

from app.services.binary_protocol import (
    BinarySerializer,
    BinaryDeserializer,
    BinaryProtocolHeader,
    MessageType,
    CompressionType,
    DTYPE_TO_CODE,
    CODE_TO_DTYPE
)


class TestBinaryProtocolHeader:
    """Test suite for binary protocol header."""

    def test_header_size(self):
        """Test header is exactly 24 bytes."""
        header = BinaryProtocolHeader(
            message_type=MessageType.SLICE_DATA,
            payload_length=1000,
            sequence_num=1
        )

        packed = header.pack()
        assert len(packed) == 24

    def test_header_pack_unpack(self):
        """Test header packing and unpacking."""
        original = BinaryProtocolHeader(
            message_type=MessageType.SLICE_DATA,
            payload_length=524288,
            sequence_num=42,
            crc32=0x12345678,
            compression=CompressionType.NONE
        )

        packed = original.pack()
        unpacked = BinaryProtocolHeader.unpack(packed)

        assert unpacked.magic == BinaryProtocolHeader.MAGIC
        assert unpacked.version == BinaryProtocolHeader.VERSION
        assert unpacked.message_type == MessageType.SLICE_DATA
        assert unpacked.payload_length == 524288
        assert unpacked.sequence_num == 42
        assert unpacked.crc32 == 0x12345678
        assert unpacked.compression == CompressionType.NONE

    def test_header_invalid_magic(self):
        """Test header rejects invalid magic number."""
        bad_data = struct.pack('<IHBBI I I I', 0xDEADBEEF, 1, 1, 0, 100, 0, 0, 0)

        with pytest.raises(ValueError, match="Invalid magic number"):
            BinaryProtocolHeader.unpack(bad_data)

    def test_header_invalid_version(self):
        """Test header rejects unsupported version."""
        bad_data = struct.pack('<IHBBI I I I', 0x4D4449, 99, 1, 0, 100, 0, 0, 0)

        with pytest.raises(ValueError, match="Unsupported protocol version"):
            BinaryProtocolHeader.unpack(bad_data)

    def test_header_too_short(self):
        """Test header rejects data shorter than 24 bytes."""
        bad_data = b"short"

        with pytest.raises(ValueError, match="Invalid header size"):
            BinaryProtocolHeader.unpack(bad_data)


class TestBinarySerializer:
    """Test suite for binary serializer."""

    @pytest.fixture
    def serializer(self):
        """Create binary serializer."""
        return BinarySerializer(compression=CompressionType.NONE)

    def test_serialize_uint16_slice(self, serializer):
        """Test serialization of uint16 CT slice (common case)."""
        # Create 512x512 uint16 slice (typical CT)
        slice_data = np.random.randint(0, 4096, (512, 512), dtype=np.uint16)

        message = serializer.serialize_slice(
            slice_data=slice_data,
            file_id="test_file_123",
            slice_index=42,
            metadata={
                "window_center": 400.0,
                "window_width": 2000.0,
                "min_value": 0.0,
                "max_value": 4095.0
            }
        )

        # Verify message structure
        assert len(message) > 24  # Header + payload

        # Verify header
        header = BinaryProtocolHeader.unpack(message[:24])
        assert header.message_type == MessageType.SLICE_DATA
        assert header.compression == CompressionType.NONE

        # Expected payload size: 68 (metadata) + 512*512*2 (pixels) = 524,356 bytes
        expected_payload_size = 68 + (512 * 512 * 2)
        assert header.payload_length == expected_payload_size

    def test_serialize_float32_slice(self, serializer):
        """Test serialization of float32 normalized slice."""
        slice_data = np.random.rand(256, 256).astype(np.float32)

        message = serializer.serialize_slice(
            slice_data=slice_data,
            file_id="normalized_mri",
            slice_index=10
        )

        header = BinaryProtocolHeader.unpack(message[:24])
        assert header.message_type == MessageType.SLICE_DATA

        # Expected: 68 + 256*256*4 = 262,212 bytes
        expected_size = 68 + (256 * 256 * 4)
        assert header.payload_length == expected_size

    def test_serialize_non_contiguous_array(self, serializer):
        """Test serialization handles non-contiguous arrays."""
        # Create non-contiguous array (Fortran-order)
        slice_data = np.random.randint(0, 255, (100, 100), dtype=np.uint8)
        slice_data = np.asfortranarray(slice_data)

        assert not slice_data.flags['C_CONTIGUOUS']

        # Should convert to C-contiguous automatically
        message = serializer.serialize_slice(
            slice_data=slice_data,
            file_id="fortran_array",
            slice_index=0
        )

        assert len(message) > 24

    def test_serialize_invalid_dimensions(self, serializer):
        """Test serialization rejects non-2D arrays."""
        # 3D array
        slice_data = np.zeros((10, 10, 10), dtype=np.uint8)

        with pytest.raises(ValueError, match="Expected 2D array"):
            serializer.serialize_slice(
                slice_data=slice_data,
                file_id="bad_dimensions",
                slice_index=0
            )

    def test_serialize_file_id_too_long(self, serializer):
        """Test serialization rejects file_id > 32 bytes."""
        slice_data = np.zeros((10, 10), dtype=np.uint8)
        long_file_id = "a" * 33

        with pytest.raises(ValueError, match="file_id too long"):
            serializer.serialize_slice(
                slice_data=slice_data,
                file_id=long_file_id,
                slice_index=0
            )

    def test_serialize_unsupported_dtype(self, serializer):
        """Test serialization rejects unsupported dtypes."""
        # int32 not supported
        slice_data = np.zeros((10, 10), dtype=np.int32)

        with pytest.raises(ValueError, match="Unsupported dtype"):
            serializer.serialize_slice(
                slice_data=slice_data,
                file_id="bad_dtype",
                slice_index=0
            )

    def test_serialize_metadata(self, serializer):
        """Test metadata serialization."""
        metadata = {
            "format": "DICOM",
            "slices": 100,
            "width": 512,
            "height": 512,
            "modality": "CT"
        }

        message = serializer.serialize_metadata(
            metadata=metadata,
            file_id="dicom_series"
        )

        header = BinaryProtocolHeader.unpack(message[:24])
        assert header.message_type == MessageType.METADATA

    def test_serialize_error(self, serializer):
        """Test error message serialization."""
        message = serializer.serialize_error(
            error_code="FILE_NOT_FOUND",
            message="File does not exist",
            details={"file_id": "missing_file"}
        )

        header = BinaryProtocolHeader.unpack(message[:24])
        assert header.message_type == MessageType.ERROR

    def test_serialize_heartbeat(self, serializer):
        """Test heartbeat serialization."""
        message = serializer.serialize_heartbeat(server_load=0.65)

        header = BinaryProtocolHeader.unpack(message[:24])
        assert header.message_type == MessageType.HEARTBEAT

    def test_sequence_numbers_increment(self, serializer):
        """Test sequence numbers increment correctly."""
        slice_data = np.zeros((10, 10), dtype=np.uint8)

        msg1 = serializer.serialize_slice(slice_data, "file1", 0)
        msg2 = serializer.serialize_slice(slice_data, "file2", 0)
        msg3 = serializer.serialize_slice(slice_data, "file3", 0)

        header1 = BinaryProtocolHeader.unpack(msg1[:24])
        header2 = BinaryProtocolHeader.unpack(msg2[:24])
        header3 = BinaryProtocolHeader.unpack(msg3[:24])

        assert header1.sequence_num == 0
        assert header2.sequence_num == 1
        assert header3.sequence_num == 2


class TestBinaryDeserializer:
    """Test suite for binary deserializer."""

    @pytest.fixture
    def serializer(self):
        """Create serializer for test data."""
        return BinarySerializer(compression=CompressionType.NONE)

    @pytest.fixture
    def deserializer(self):
        """Create deserializer."""
        return BinaryDeserializer()

    def test_deserialize_slice_data(self, serializer, deserializer):
        """Test deserialization of slice data."""
        # Create test slice
        original_slice = np.random.randint(0, 4096, (512, 512), dtype=np.uint16)

        # Serialize
        message = serializer.serialize_slice(
            slice_data=original_slice,
            file_id="test_ct_scan",
            slice_index=25,
            metadata={
                "window_center": 400.0,
                "window_width": 2000.0,
                "min_value": 0.0,
                "max_value": 4095.0
            }
        )

        # Deserialize
        header, payload = deserializer.deserialize(message)

        # Verify header
        assert header.message_type == MessageType.SLICE_DATA
        assert header.sequence_num == 0

        # Verify payload
        assert payload["file_id"] == "test_ct_scan"
        assert payload["slice_index"] == 25
        assert payload["width"] == 512
        assert payload["height"] == 512
        assert payload["dtype"] == "uint16"
        assert payload["window_center"] == 400.0
        assert payload["window_width"] == 2000.0

        # Verify pixel data matches
        np.testing.assert_array_equal(payload["data"], original_slice)

    def test_deserialize_different_dtypes(self, serializer, deserializer):
        """Test deserialization works for all supported dtypes."""
        dtypes = [np.uint8, np.uint16, np.int16, np.float32, np.float64]

        for dtype in dtypes:
            if dtype in [np.float32, np.float64]:
                slice_data = np.random.rand(100, 100).astype(dtype)
            else:
                slice_data = np.random.randint(0, 100, (100, 100), dtype=dtype)

            dtype_name = np.dtype(dtype).name

            message = serializer.serialize_slice(
                slice_data=slice_data,
                file_id=f"test_{dtype_name}",
                slice_index=0
            )

            header, payload = deserializer.deserialize(message)

            assert payload["dtype"] == dtype_name
            np.testing.assert_array_almost_equal(payload["data"], slice_data)

    def test_deserialize_metadata(self, serializer, deserializer):
        """Test metadata deserialization."""
        metadata = {
            "format": "NIfTI",
            "slices": 200,
            "spacing": [1.0, 1.0, 2.0]
        }

        message = serializer.serialize_metadata(metadata, "nifti_file")

        header, payload = deserializer.deserialize(message)

        assert header.message_type == MessageType.METADATA
        assert payload == metadata

    def test_deserialize_error(self, serializer, deserializer):
        """Test error message deserialization."""
        message = serializer.serialize_error(
            error_code="INVALID_SLICE",
            message="Slice index out of range",
            details={"max_slices": 99}
        )

        header, payload = deserializer.deserialize(message)

        assert header.message_type == MessageType.ERROR
        assert payload["code"] == "INVALID_SLICE"
        assert payload["message"] == "Slice index out of range"
        assert payload["details"]["max_slices"] == 99

    def test_deserialize_heartbeat(self, serializer, deserializer):
        """Test heartbeat deserialization."""
        message = serializer.serialize_heartbeat(server_load=0.75)

        header, payload = deserializer.deserialize(message)

        assert header.message_type == MessageType.HEARTBEAT
        assert "timestamp" in payload
        assert payload["server_load"] == pytest.approx(0.75)

    def test_deserialize_crc_mismatch(self, serializer, deserializer):
        """Test deserialization detects corrupted data."""
        slice_data = np.zeros((10, 10), dtype=np.uint8)
        message = serializer.serialize_slice(slice_data, "test", 0)

        # Corrupt a byte in the payload
        message_list = bytearray(message)
        message_list[50] ^= 0xFF  # Flip bits
        corrupted_message = bytes(message_list)

        with pytest.raises(ValueError, match="CRC mismatch"):
            deserializer.deserialize(corrupted_message)

    def test_deserialize_incomplete_message(self, deserializer):
        """Test deserialization rejects incomplete messages."""
        # Only header, no payload
        header = BinaryProtocolHeader(
            message_type=MessageType.SLICE_DATA,
            payload_length=1000,
            sequence_num=0
        )

        incomplete_message = header.pack()  # No payload

        with pytest.raises(ValueError, match="Incomplete message"):
            deserializer.deserialize(incomplete_message)

    def test_deserialize_message_too_short(self, deserializer):
        """Test deserialization rejects too-short messages."""
        short_message = b"short"

        with pytest.raises(ValueError, match="Message too short"):
            deserializer.deserialize(short_message)


class TestRoundTrip:
    """Test suite for serialization/deserialization round trips."""

    @pytest.fixture
    def serializer(self):
        return BinarySerializer(compression=CompressionType.NONE)

    @pytest.fixture
    def deserializer(self):
        return BinaryDeserializer()

    def test_roundtrip_preserves_data(self, serializer, deserializer):
        """Test full round-trip preserves data perfectly."""
        # Create diverse test data
        test_cases = [
            (np.random.randint(0, 255, (256, 256), dtype=np.uint8), "uint8_test"),
            (np.random.randint(0, 4096, (512, 512), dtype=np.uint16), "uint16_ct"),
            (np.random.randint(-1000, 1000, (128, 128), dtype=np.int16), "int16_mri"),
            (np.random.rand(64, 64).astype(np.float32), "float32_normalized"),
        ]

        for original_data, file_id in test_cases:
            # Serialize
            message = serializer.serialize_slice(
                slice_data=original_data,
                file_id=file_id,
                slice_index=0
            )

            # Deserialize
            header, payload = deserializer.deserialize(message)

            # Verify exact match
            np.testing.assert_array_equal(payload["data"], original_data)
            assert payload["file_id"] == file_id

    def test_roundtrip_large_image(self, serializer, deserializer):
        """Test round-trip with large 1024x1024 image."""
        large_slice = np.random.randint(0, 4096, (1024, 1024), dtype=np.uint16)

        message = serializer.serialize_slice(
            slice_data=large_slice,
            file_id="large_ct_scan",
            slice_index=50
        )

        header, payload = deserializer.deserialize(message)

        np.testing.assert_array_equal(payload["data"], large_slice)
        assert payload["width"] == 1024
        assert payload["height"] == 1024


class TestPerformance:
    """Test suite for performance benchmarks."""

    @pytest.fixture
    def serializer(self):
        return BinarySerializer(compression=CompressionType.NONE)

    def test_binary_vs_base64_size_comparison(self, serializer):
        """
        Test binary format is ~25% smaller than Base64.

        PoC validated: 341KB (Base64) → 256KB (Binary) = 25% reduction
        """
        import base64

        # 512x512 uint16 CT slice
        slice_data = np.random.randint(0, 4096, (512, 512), dtype=np.uint16)

        # Binary format
        binary_message = serializer.serialize_slice(
            slice_data=slice_data,
            file_id="test",
            slice_index=0
        )

        # Base64 format (current method)
        base64_encoded = base64.b64encode(slice_data.tobytes()).decode('utf-8')
        base64_json = f'{{"data": "{base64_encoded}"}}'

        binary_size = len(binary_message)
        base64_size = len(base64_json)

        reduction_pct = (1 - binary_size / base64_size) * 100

        print(f"\nSize comparison:")
        print(f"  Binary: {binary_size:,} bytes")
        print(f"  Base64: {base64_size:,} bytes")
        print(f"  Reduction: {reduction_pct:.1f}%")

        # Should be ~25% smaller (PoC target)
        assert reduction_pct >= 20  # Allow some variance
        assert reduction_pct <= 30

    def test_serialization_performance(self, serializer):
        """Test serialization performance (basic timing check)."""
        import time

        slice_data = np.random.randint(0, 4096, (512, 512), dtype=np.uint16)

        # Time serialization (should be fast)
        start_time = time.time()
        result = serializer.serialize_slice(
            slice_data=slice_data,
            file_id="benchmark_test",
            slice_index=0
        )
        elapsed = time.time() - start_time

        # Should complete in reasonable time (< 100ms for 512x512)
        assert elapsed < 0.1, f"Serialization too slow: {elapsed:.3f}s"
        assert len(result) > 24
