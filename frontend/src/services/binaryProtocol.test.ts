/**
 * Unit tests for Binary Protocol Implementation (Frontend).
 *
 * Tests deserialization of medical images in binary format.
 * Validates compatibility with backend BinarySerializer.
 *
 * @vitest-environment node
 */

import { describe, it, expect } from 'vitest';
import {
  BinaryDeserializer,
  MessageType,
  CompressionType,
  type BinaryProtocolHeader,
  type SliceDataPayload,
} from './binaryProtocol';

/**
 * Helper: Create a binary protocol header.
 */
function createHeader(
  messageType: MessageType,
  payloadLength: number,
  sequenceNum: number = 0,
  crc32: number = 0,
  compression: CompressionType = CompressionType.NONE
): ArrayBuffer {
  const buffer = new ArrayBuffer(24);
  const view = new DataView(buffer);

  view.setUint32(0, 0x4d4449, true); // magic = "MDI"
  view.setUint16(4, 1, true); // version = 1
  view.setUint8(6, messageType);
  view.setUint8(7, compression);
  view.setUint32(8, payloadLength, true);
  view.setUint32(12, sequenceNum, true);
  view.setUint32(16, crc32, true);
  view.setUint32(20, 0, true); // reserved

  return buffer;
}

/**
 * Helper: Calculate CRC32 checksum (must match backend implementation).
 */
function calculateCRC32(data: Uint8Array): number {
  const crcTable: number[] = [];

  // Generate CRC table
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
    crcTable[n] = c;
  }

  let crc = 0 ^ -1;

  for (let i = 0; i < data.length; i++) {
    crc = (crc >>> 8) ^ crcTable[(crc ^ data[i]) & 0xff];
  }

  return (crc ^ -1) >>> 0;
}

/**
 * Helper: Create slice metadata header (68 bytes).
 */
function createSliceMetadataHeader(
  fileId: string,
  sliceIndex: number,
  width: number,
  height: number,
  dtypeCode: number,
  minValue: number = 0,
  maxValue: number = 4095,
  windowCenter: number = 0,
  windowWidth: number = 0
): ArrayBuffer {
  const buffer = new ArrayBuffer(68);
  const view = new DataView(buffer);

  // file_id (32 bytes, UTF-8, zero-padded)
  const encoder = new TextEncoder();
  const fileIdBytes = encoder.encode(fileId);
  const fileIdArray = new Uint8Array(buffer, 0, 32);
  fileIdArray.set(fileIdBytes.slice(0, 32));

  // Metadata fields
  view.setUint32(32, sliceIndex, true);
  view.setUint32(36, width, true);
  view.setUint32(40, height, true);
  view.setUint32(44, dtypeCode, true);
  view.setFloat32(48, minValue, true);
  view.setFloat32(52, maxValue, true);
  view.setFloat32(56, windowCenter, true);
  view.setFloat32(60, windowWidth, true);
  view.setUint32(64, 0, true); // reserved

  return buffer;
}

/**
 * Helper: Concatenate ArrayBuffers.
 */
function concatBuffers(...buffers: ArrayBuffer[]): ArrayBuffer {
  const totalLength = buffers.reduce((sum, buf) => sum + buf.byteLength, 0);
  const result = new Uint8Array(totalLength);

  let offset = 0;
  for (const buffer of buffers) {
    result.set(new Uint8Array(buffer), offset);
    offset += buffer.byteLength;
  }

  return result.buffer;
}

describe('BinaryProtocolHeader', () => {
  const deserializer = new BinaryDeserializer();

  it('should deserialize valid header correctly', () => {
    // Use METADATA message for simple header validation (JSON payload)
    const metadata = { test: 'data' };
    const encoder = new TextEncoder();
    const payloadBytes = encoder.encode(JSON.stringify(metadata));
    const crc = calculateCRC32(payloadBytes);

    const headerBuffer = createHeader(
      MessageType.METADATA,
      payloadBytes.length,
      42,
      crc,
      CompressionType.NONE
    );

    const message = concatBuffers(headerBuffer, payloadBytes.buffer);
    const result = deserializer.deserialize(message);

    expect(result.header.magic).toBe(0x4d4449);
    expect(result.header.version).toBe(1);
    expect(result.header.messageType).toBe(MessageType.METADATA);
    expect(result.header.payloadLength).toBe(payloadBytes.length);
    expect(result.header.sequenceNum).toBe(42);
    expect(result.header.compression).toBe(CompressionType.NONE);
    expect(result.payload).toEqual(metadata);
  });

  it('should reject invalid magic number', () => {
    const buffer = new ArrayBuffer(24);
    const view = new DataView(buffer);

    view.setUint32(0, 0xdeadbeef, true); // Invalid magic
    view.setUint16(4, 1, true);
    view.setUint8(6, MessageType.SLICE_DATA);
    view.setUint8(7, CompressionType.NONE);
    view.setUint32(8, 100, true);
    view.setUint32(12, 0, true);
    view.setUint32(16, 0, true);
    view.setUint32(20, 0, true);

    expect(() => {
      deserializer.deserialize(buffer);
    }).toThrow('Invalid magic number');
  });

  it('should reject unsupported version', () => {
    const buffer = new ArrayBuffer(24);
    const view = new DataView(buffer);

    view.setUint32(0, 0x4d4449, true);
    view.setUint16(4, 99, true); // Unsupported version
    view.setUint8(6, MessageType.SLICE_DATA);
    view.setUint8(7, CompressionType.NONE);
    view.setUint32(8, 100, true);
    view.setUint32(12, 0, true);
    view.setUint32(16, 0, true);
    view.setUint32(20, 0, true);

    expect(() => {
      deserializer.deserialize(buffer);
    }).toThrow('Unsupported protocol version');
  });

  it('should reject message shorter than 24 bytes', () => {
    const buffer = new ArrayBuffer(10);

    expect(() => {
      deserializer.deserialize(buffer);
    }).toThrow('Message too short');
  });
});

describe('BinaryDeserializer - Slice Data', () => {
  const deserializer = new BinaryDeserializer();

  it('should deserialize uint16 slice correctly', () => {
    const width = 512;
    const height = 512;
    const dtypeCode = 0x02; // uint16

    // Create test pixel data
    const pixelData = new Uint16Array(width * height);
    for (let i = 0; i < pixelData.length; i++) {
      pixelData[i] = i % 4096;
    }

    // Build payload
    const metadataHeader = createSliceMetadataHeader(
      'test_ct_scan',
      25,
      width,
      height,
      dtypeCode,
      0,
      4095,
      400,
      2000
    );

    const payload = concatBuffers(metadataHeader, pixelData.buffer);
    const payloadBytes = new Uint8Array(payload);
    const crc = calculateCRC32(payloadBytes);

    // Build header
    const header = createHeader(
      MessageType.SLICE_DATA,
      payload.byteLength,
      0,
      crc,
      CompressionType.NONE
    );

    // Build complete message
    const message = concatBuffers(header, payload);

    // Deserialize
    const result = deserializer.deserialize(message);

    expect(result.header.messageType).toBe(MessageType.SLICE_DATA);

    const slicePayload = result.payload as SliceDataPayload;
    expect(slicePayload.fileId).toBe('test_ct_scan');
    expect(slicePayload.sliceIndex).toBe(25);
    expect(slicePayload.width).toBe(512);
    expect(slicePayload.height).toBe(512);
    expect(slicePayload.dtype).toBe('uint16');
    expect(slicePayload.minValue).toBeCloseTo(0);
    expect(slicePayload.maxValue).toBeCloseTo(4095);
    expect(slicePayload.windowCenter).toBeCloseTo(400);
    expect(slicePayload.windowWidth).toBeCloseTo(2000);

    // Verify pixel data
    expect(slicePayload.data).toBeInstanceOf(Uint16Array);
    expect(slicePayload.data.length).toBe(width * height);

    const deserializedPixels = slicePayload.data as Uint16Array;
    for (let i = 0; i < 100; i++) {
      // Check first 100 pixels
      expect(deserializedPixels[i]).toBe(pixelData[i]);
    }
  });

  it('should deserialize uint8 slice correctly', () => {
    const width = 256;
    const height = 256;
    const dtypeCode = 0x01; // uint8

    const pixelData = new Uint8Array(width * height);
    for (let i = 0; i < pixelData.length; i++) {
      pixelData[i] = i % 256;
    }

    const metadataHeader = createSliceMetadataHeader(
      'test_mri',
      10,
      width,
      height,
      dtypeCode
    );

    const payload = concatBuffers(metadataHeader, pixelData.buffer);
    const payloadBytes = new Uint8Array(payload);
    const crc = calculateCRC32(payloadBytes);

    const header = createHeader(
      MessageType.SLICE_DATA,
      payload.byteLength,
      0,
      crc
    );

    const message = concatBuffers(header, payload);
    const result = deserializer.deserialize(message);

    const slicePayload = result.payload as SliceDataPayload;
    expect(slicePayload.dtype).toBe('uint8');
    expect(slicePayload.data).toBeInstanceOf(Uint8Array);
    expect(slicePayload.data.length).toBe(width * height);
  });

  it('should deserialize float32 slice correctly', () => {
    const width = 128;
    const height = 128;
    const dtypeCode = 0x04; // float32

    const pixelData = new Float32Array(width * height);
    for (let i = 0; i < pixelData.length; i++) {
      pixelData[i] = Math.random();
    }

    const metadataHeader = createSliceMetadataHeader(
      'normalized_slice',
      5,
      width,
      height,
      dtypeCode
    );

    const payload = concatBuffers(metadataHeader, pixelData.buffer);
    const payloadBytes = new Uint8Array(payload);
    const crc = calculateCRC32(payloadBytes);

    const header = createHeader(
      MessageType.SLICE_DATA,
      payload.byteLength,
      0,
      crc
    );

    const message = concatBuffers(header, payload);
    const result = deserializer.deserialize(message);

    const slicePayload = result.payload as SliceDataPayload;
    expect(slicePayload.dtype).toBe('float32');
    expect(slicePayload.data).toBeInstanceOf(Float32Array);
    expect(slicePayload.data.length).toBe(width * height);
  });

  it('should detect CRC mismatch', () => {
    const width = 64;
    const height = 64;
    const dtypeCode = 0x01;

    const pixelData = new Uint8Array(width * height).fill(0);
    const metadataHeader = createSliceMetadataHeader(
      'test',
      0,
      width,
      height,
      dtypeCode
    );

    const payload = concatBuffers(metadataHeader, pixelData.buffer);

    // Use WRONG CRC
    const header = createHeader(
      MessageType.SLICE_DATA,
      payload.byteLength,
      0,
      0x12345678 // Wrong CRC
    );

    const message = concatBuffers(header, payload);

    expect(() => {
      deserializer.deserialize(message);
    }).toThrow('CRC mismatch');
  });

  it('should reject incomplete slice payload', () => {
    const width = 512;
    const height = 512;
    const dtypeCode = 0x02; // uint16

    // Create incomplete pixel data (only half)
    const pixelData = new Uint16Array((width * height) / 2);

    const metadataHeader = createSliceMetadataHeader(
      'incomplete',
      0,
      width,
      height,
      dtypeCode
    );

    const payload = concatBuffers(metadataHeader, pixelData.buffer);
    const payloadBytes = new Uint8Array(payload);
    const crc = calculateCRC32(payloadBytes);

    const header = createHeader(
      MessageType.SLICE_DATA,
      payload.byteLength,
      0,
      crc
    );

    const message = concatBuffers(header, payload);

    expect(() => {
      deserializer.deserialize(message);
    }).toThrow('Invalid pixel data size');
  });
});

describe('BinaryDeserializer - Metadata', () => {
  const deserializer = new BinaryDeserializer();

  it('should deserialize metadata correctly', () => {
    const metadata = {
      format: 'DICOM',
      slices: 100,
      width: 512,
      height: 512,
      modality: 'CT',
    };

    const encoder = new TextEncoder();
    const payloadBytes = encoder.encode(JSON.stringify(metadata));
    const crc = calculateCRC32(payloadBytes);

    const header = createHeader(
      MessageType.METADATA,
      payloadBytes.length,
      0,
      crc
    );

    const message = concatBuffers(header, payloadBytes.buffer);
    const result = deserializer.deserialize(message);

    expect(result.header.messageType).toBe(MessageType.METADATA);
    expect(result.payload).toEqual(metadata);
  });
});

describe('BinaryDeserializer - Error', () => {
  const deserializer = new BinaryDeserializer();

  it('should deserialize error message correctly', () => {
    const error = {
      code: 'FILE_NOT_FOUND',
      message: 'File does not exist',
      details: { file_id: 'missing_file' },
    };

    const encoder = new TextEncoder();
    const payloadBytes = encoder.encode(JSON.stringify(error));
    const crc = calculateCRC32(payloadBytes);

    const header = createHeader(
      MessageType.ERROR,
      payloadBytes.length,
      0,
      crc
    );

    const message = concatBuffers(header, payloadBytes.buffer);
    const result = deserializer.deserialize(message);

    expect(result.header.messageType).toBe(MessageType.ERROR);
    expect(result.payload).toEqual(error);
  });
});

describe('BinaryDeserializer - Heartbeat', () => {
  const deserializer = new BinaryDeserializer();

  it('should deserialize heartbeat correctly', () => {
    const payload = new ArrayBuffer(12);
    const view = new DataView(payload);

    // timestamp (uint64, split into two uint32s)
    const timestampMs = 1234567890123;
    const timestampLow = timestampMs & 0xffffffff;
    const timestampHigh = Math.floor(timestampMs / 0x100000000);
    view.setUint32(0, timestampLow, true);
    view.setUint32(4, timestampHigh, true);

    // server_load (float32)
    view.setFloat32(8, 0.75, true);

    const payloadBytes = new Uint8Array(payload);
    const crc = calculateCRC32(payloadBytes);

    const header = createHeader(MessageType.HEARTBEAT, 12, 0, crc);

    const message = concatBuffers(header, payload);
    const result = deserializer.deserialize(message);

    expect(result.header.messageType).toBe(MessageType.HEARTBEAT);

    const heartbeat = result.payload as any;
    expect(heartbeat.timestamp).toBe(timestampMs);
    expect(heartbeat.serverLoad).toBeCloseTo(0.75);
  });
});

describe('BinaryDeserializer - Round Trip Compatibility', () => {
  const deserializer = new BinaryDeserializer();

  it('should match backend serialization format for uint16 CT slice', () => {
    // This test validates format compatibility with backend
    const width = 512;
    const height = 512;
    const dtypeCode = 0x02; // uint16

    // Create test data matching backend test
    const pixelData = new Uint16Array(width * height);
    for (let i = 0; i < pixelData.length; i++) {
      pixelData[i] = (i * 17) % 4096; // Deterministic pattern
    }

    const metadataHeader = createSliceMetadataHeader(
      'round_trip_test',
      42,
      width,
      height,
      dtypeCode,
      0,
      4095,
      400,
      2000
    );

    const payload = concatBuffers(metadataHeader, pixelData.buffer);
    const payloadBytes = new Uint8Array(payload);
    const crc = calculateCRC32(payloadBytes);

    const header = createHeader(
      MessageType.SLICE_DATA,
      payload.byteLength,
      0,
      crc
    );

    const message = concatBuffers(header, payload);

    // Deserialize and verify
    const result = deserializer.deserialize(message);

    const slicePayload = result.payload as SliceDataPayload;
    expect(slicePayload.fileId).toBe('round_trip_test');
    expect(slicePayload.sliceIndex).toBe(42);
    expect(slicePayload.width).toBe(width);
    expect(slicePayload.height).toBe(height);
    expect(slicePayload.dtype).toBe('uint16');

    // Verify exact pixel data match
    const deserializedPixels = slicePayload.data as Uint16Array;
    for (let i = 0; i < pixelData.length; i++) {
      expect(deserializedPixels[i]).toBe(pixelData[i]);
    }
  });
});
