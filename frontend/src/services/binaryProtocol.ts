/**
 * Binary Protocol Implementation for Medical Image Transfer (Frontend).
 *
 * TypeScript implementation of the binary protocol for efficient medical image
 * deserialization, achieving 17-42x speedup over Base64 (PoC validated).
 *
 * Protocol Specification: See BINARY_PROTOCOL_SPEC.md
 */

/**
 * Binary protocol message types.
 */
export enum MessageType {
  SLICE_DATA = 0x01, // Medical image slice data
  METADATA = 0x02, // Image metadata
  ERROR = 0x03, // Error message
  HEARTBEAT = 0x04, // Connection heartbeat
  ACK = 0x05, // Acknowledgment
}

/**
 * Compression algorithms.
 */
export enum CompressionType {
  NONE = 0x00, // No compression
  ZLIB = 0x01, // zlib compression
  LZ4 = 0x02, // LZ4 compression (fastest)
  ZSTD = 0x03, // Zstandard (best ratio)
}

/**
 * Binary protocol dtype codes to TypedArray constructors.
 */
const CODE_TO_TYPED_ARRAY: Record<number, any> = {
  0x01: Uint8Array,
  0x02: Uint16Array,
  0x03: Int16Array,
  0x04: Float32Array,
  0x05: Float64Array,
};

/**
 * dtype code to element size in bytes.
 */
const DTYPE_SIZES: Record<number, number> = {
  0x01: 1, // uint8
  0x02: 2, // uint16
  0x03: 2, // int16
  0x04: 4, // float32
  0x05: 8, // float64
};

/**
 * dtype code to string name.
 */
const DTYPE_NAMES: Record<number, string> = {
  0x01: 'uint8',
  0x02: 'uint16',
  0x03: 'int16',
  0x04: 'float32',
  0x05: 'float64',
};

/**
 * Binary protocol message header (24 bytes).
 *
 * Format (little-endian):
 *   magic (4 bytes): 0x4D4449 ("MDI" - Medical Digital Imaging)
 *   version (2 bytes): Protocol version (1)
 *   message_type (1 byte): MessageType enum
 *   compression (1 byte): CompressionType enum
 *   payload_length (4 bytes): Payload size in bytes
 *   sequence_num (4 bytes): Sequence number
 *   crc32 (4 bytes): Payload CRC32 checksum
 *   reserved (4 bytes): Reserved for future use
 */
export interface BinaryProtocolHeader {
  magic: number;
  version: number;
  messageType: MessageType;
  compression: CompressionType;
  payloadLength: number;
  sequenceNum: number;
  crc32: number;
  reserved: number;
}

/**
 * Slice data payload.
 */
export interface SliceDataPayload {
  fileId: string;
  sliceIndex: number;
  width: number;
  height: number;
  dtype: string;
  minValue: number;
  maxValue: number;
  windowCenter: number;
  windowWidth: number;
  data: Uint8Array | Uint16Array | Int16Array | Float32Array | Float64Array;
}

/**
 * Metadata payload.
 */
export interface MetadataPayload {
  [key: string]: any;
}

/**
 * Error payload.
 */
export interface ErrorPayload {
  code: string;
  message: string;
  details: Record<string, any>;
}

/**
 * Heartbeat payload.
 */
export interface HeartbeatPayload {
  timestamp: number;
  serverLoad: number;
}

/**
 * Deserialized message.
 */
export interface DeserializedMessage {
  header: BinaryProtocolHeader;
  payload:
    | SliceDataPayload
    | MetadataPayload
    | ErrorPayload
    | HeartbeatPayload;
}

/**
 * Binary protocol header constants.
 */
const MAGIC = 0x4d4449; // "MDI"
const VERSION = 1;
const HEADER_SIZE = 24;

/**
 * Binary protocol deserializer for medical images.
 *
 * Deserializes binary messages from the backend into TypedArrays for
 * efficient rendering with Canvas/WebGL.
 */
export class BinaryDeserializer {
  /**
   * Initialize binary deserializer.
   */
  constructor() {
    console.log('[BinaryDeserializer] Initialized');
  }

  /**
   * Deserialize a binary message.
   *
   * @param data - Complete binary message (header + payload)
   * @returns Deserialized message with header and payload
   * @throws Error if message is invalid or corrupted
   */
  deserialize(data: ArrayBuffer): DeserializedMessage {
    if (data.byteLength < HEADER_SIZE) {
      throw new Error(
        `Message too short: ${data.byteLength} bytes (expected >= ${HEADER_SIZE})`
      );
    }

    // Parse header
    const header = this.unpackHeader(data);

    // Extract payload
    const payloadStart = HEADER_SIZE;
    const payloadEnd = payloadStart + header.payloadLength;

    if (data.byteLength < payloadEnd) {
      throw new Error(
        `Incomplete message: expected ${payloadEnd} bytes, got ${data.byteLength}`
      );
    }

    let payload = data.slice(payloadStart, payloadEnd);

    // Verify CRC32
    const calculatedCrc = this.calculateCRC32(new Uint8Array(payload));
    if (calculatedCrc !== header.crc32) {
      throw new Error(
        `CRC mismatch: expected 0x${header.crc32.toString(16).padStart(8, '0')}, got 0x${calculatedCrc.toString(16).padStart(8, '0')}`
      );
    }

    // Decompress if needed
    if (header.compression !== CompressionType.NONE) {
      payload = this.decompress(payload, header.compression);
    }

    // Deserialize based on message type
    let deserializedPayload:
      | SliceDataPayload
      | MetadataPayload
      | ErrorPayload
      | HeartbeatPayload;

    switch (header.messageType) {
      case MessageType.SLICE_DATA:
        deserializedPayload = this.deserializeSlice(payload);
        break;
      case MessageType.METADATA:
        deserializedPayload = this.deserializeMetadata(payload);
        break;
      case MessageType.ERROR:
        deserializedPayload = this.deserializeError(payload);
        break;
      case MessageType.HEARTBEAT:
        deserializedPayload = this.deserializeHeartbeat(payload);
        break;
      default:
        throw new Error(`Unknown message type: ${header.messageType}`);
    }

    return {
      header,
      payload: deserializedPayload,
    };
  }

  /**
   * Unpack binary protocol header from ArrayBuffer.
   *
   * @param data - Binary data containing header
   * @returns Parsed header
   * @throws Error if header is invalid
   */
  private unpackHeader(data: ArrayBuffer): BinaryProtocolHeader {
    const view = new DataView(data, 0, HEADER_SIZE);

    const magic = view.getUint32(0, true); // Little-endian
    const version = view.getUint16(4, true);
    const messageType = view.getUint8(6);
    const compression = view.getUint8(7);
    const payloadLength = view.getUint32(8, true);
    const sequenceNum = view.getUint32(12, true);
    const crc32 = view.getUint32(16, true);
    const reserved = view.getUint32(20, true);

    // Validate magic number
    if (magic !== MAGIC) {
      throw new Error(`Invalid magic number: 0x${magic.toString(16)}`);
    }

    // Validate version
    if (version !== VERSION) {
      throw new Error(`Unsupported protocol version: ${version}`);
    }

    return {
      magic,
      version,
      messageType,
      compression,
      payloadLength,
      sequenceNum,
      crc32,
      reserved,
    };
  }

  /**
   * Deserialize SLICE_DATA payload.
   *
   * @param payload - Slice data payload (metadata header + pixel data)
   * @returns Deserialized slice data
   */
  private deserializeSlice(payload: ArrayBuffer): SliceDataPayload {
    const METADATA_HEADER_SIZE = 68;

    if (payload.byteLength < METADATA_HEADER_SIZE) {
      throw new Error(
        `Slice payload too short: ${payload.byteLength} bytes`
      );
    }

    const view = new DataView(payload, 0, METADATA_HEADER_SIZE);

    // Parse metadata header (68 bytes)
    // file_id: 32 bytes (UTF-8 string, zero-padded)
    const fileIdBytes = new Uint8Array(payload, 0, 32);
    const fileId = this.decodeNullTerminatedString(fileIdBytes);

    // Remaining fields (little-endian)
    const sliceIndex = view.getUint32(32, true);
    const width = view.getUint32(36, true);
    const height = view.getUint32(40, true);
    const dtypeCode = view.getUint32(44, true);
    const minValue = view.getFloat32(48, true);
    const maxValue = view.getFloat32(52, true);
    const windowCenter = view.getFloat32(56, true);
    const windowWidth = view.getFloat32(60, true);
    // reserved = view.getUint32(64, true);

    // Get dtype info
    const TypedArrayConstructor = CODE_TO_TYPED_ARRAY[dtypeCode];
    const dtype = DTYPE_NAMES[dtypeCode];

    if (!TypedArrayConstructor || !dtype) {
      throw new Error(`Unknown dtype code: ${dtypeCode}`);
    }

    // Calculate expected pixel data size
    const elementSize = DTYPE_SIZES[dtypeCode];
    const expectedSize = width * height * elementSize;
    const pixelDataBuffer = payload.slice(METADATA_HEADER_SIZE);

    if (pixelDataBuffer.byteLength !== expectedSize) {
      throw new Error(
        `Invalid pixel data size: expected ${expectedSize}, got ${pixelDataBuffer.byteLength}`
      );
    }

    // Create TypedArray view of pixel data
    const data = new TypedArrayConstructor(pixelDataBuffer);

    return {
      fileId,
      sliceIndex,
      width,
      height,
      dtype,
      minValue,
      maxValue,
      windowCenter,
      windowWidth,
      data,
    };
  }

  /**
   * Deserialize METADATA payload.
   *
   * @param payload - JSON metadata
   * @returns Parsed metadata
   */
  private deserializeMetadata(payload: ArrayBuffer): MetadataPayload {
    const decoder = new TextDecoder('utf-8');
    const jsonStr = decoder.decode(payload);
    return JSON.parse(jsonStr);
  }

  /**
   * Deserialize ERROR payload.
   *
   * @param payload - JSON error data
   * @returns Parsed error
   */
  private deserializeError(payload: ArrayBuffer): ErrorPayload {
    const decoder = new TextDecoder('utf-8');
    const jsonStr = decoder.decode(payload);
    return JSON.parse(jsonStr);
  }

  /**
   * Deserialize HEARTBEAT payload.
   *
   * @param payload - Heartbeat data (timestamp + server_load)
   * @returns Parsed heartbeat
   */
  private deserializeHeartbeat(payload: ArrayBuffer): HeartbeatPayload {
    const view = new DataView(payload);

    // timestamp (uint64 - split into two uint32s for JS)
    const timestampLow = view.getUint32(0, true);
    const timestampHigh = view.getUint32(4, true);
    const timestamp = timestampHigh * 0x100000000 + timestampLow;

    // server_load (float32)
    const serverLoad = view.getFloat32(8, true);

    return {
      timestamp,
      serverLoad,
    };
  }

  /**
   * Calculate CRC32 checksum.
   *
   * @param data - Data to checksum
   * @returns CRC32 value
   */
  private calculateCRC32(data: Uint8Array): number {
    // CRC32 polynomial table (IEEE 802.3)
    const crcTable = this.makeCRCTable();

    let crc = 0 ^ -1;

    for (let i = 0; i < data.length; i++) {
      crc = (crc >>> 8) ^ crcTable[(crc ^ data[i]) & 0xff];
    }

    return (crc ^ -1) >>> 0; // Convert to unsigned 32-bit
  }

  /**
   * Generate CRC32 lookup table.
   *
   * @returns CRC32 table
   */
  private makeCRCTable(): number[] {
    const crcTable: number[] = [];

    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) {
        c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      }
      crcTable[n] = c;
    }

    return crcTable;
  }

  /**
   * Decompress payload based on compression type.
   *
   * @param payload - Compressed payload
   * @param compression - Compression type
   * @returns Decompressed payload
   */
  private decompress(
    payload: ArrayBuffer,
    compression: CompressionType
  ): ArrayBuffer {
    // Note: Browser-based decompression requires additional libraries
    // For now, we only support NONE compression
    // Future: Add pako (zlib), lz4-js, zstd-codec support

    switch (compression) {
      case CompressionType.NONE:
        return payload;

      case CompressionType.ZLIB:
        throw new Error(
          'ZLIB decompression not implemented (requires pako library)'
        );

      case CompressionType.LZ4:
        throw new Error(
          'LZ4 decompression not implemented (requires lz4-js library)'
        );

      case CompressionType.ZSTD:
        throw new Error(
          'ZSTD decompression not implemented (requires zstd-codec library)'
        );

      default:
        throw new Error(`Unknown compression type: ${compression}`);
    }
  }

  /**
   * Decode null-terminated UTF-8 string from Uint8Array.
   *
   * @param bytes - Byte array containing string
   * @returns Decoded string (without null padding)
   */
  private decodeNullTerminatedString(bytes: Uint8Array): string {
    // Find null terminator
    let length = 0;
    while (length < bytes.length && bytes[length] !== 0) {
      length++;
    }

    // Decode only the non-null portion
    const decoder = new TextDecoder('utf-8');
    return decoder.decode(bytes.slice(0, length));
  }
}

/**
 * Default binary deserializer instance.
 */
export const binaryDeserializer = new BinaryDeserializer();
