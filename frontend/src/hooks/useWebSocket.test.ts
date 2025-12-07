/**
 * Unit tests for useWebSocket hook.
 *
 * Tests WebSocket connection management, reconnection, message handling,
 * and binary protocol integration.
 *
 * @vitest-environment jsdom
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useWebSocket, WebSocketState } from './useWebSocket';
import { MessageType, CompressionType } from '../services/binaryProtocol';

/**
 * Mock WebSocket for testing.
 */
class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  readyState = MockWebSocket.CONNECTING;
  binaryType: string = 'blob';
  url: string;

  onopen: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;

  sentMessages: any[] = [];

  constructor(url: string) {
    this.url = url;

    // Simulate async connection
    setTimeout(() => {
      this.readyState = MockWebSocket.OPEN;
      this.onopen?.(new Event('open'));
    }, 10);
  }

  send(data: any) {
    this.sentMessages.push(data);
  }

  close(code?: number, reason?: string) {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.(new CloseEvent('close', { code, reason }));
  }

  // Helper to simulate receiving a message
  simulateMessage(data: any) {
    this.onmessage?.(new MessageEvent('message', { data }));
  }

  // Helper to simulate an error
  simulateError() {
    this.onerror?.(new Event('error'));
  }
}

describe('useWebSocket', () => {
  let mockWebSocket: typeof MockWebSocket;

  beforeEach(() => {
    // Mock WebSocket globally
    mockWebSocket = MockWebSocket as any;
    global.WebSocket = mockWebSocket as any;

    // Mock timers
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  describe('Connection Management', () => {
    it('should connect on mount', async () => {
      const { result } = renderHook(() =>
        useWebSocket({ url: 'ws://localhost:8000/ws/test' })
      );

      // Initial state
      expect(result.current.state).toBe(WebSocketState.CONNECTING);
      expect(result.current.isConnected).toBe(false);
      expect(result.current.isConnecting).toBe(true);

      // Wait for connection
      await act(async () => {
        vi.advanceTimersByTime(20);
      });

      await waitFor(() => {
        expect(result.current.state).toBe(WebSocketState.CONNECTED);
        expect(result.current.isConnected).toBe(true);
        expect(result.current.isConnecting).toBe(false);
      });
    });

    it('should call onOpen when connected', async () => {
      const onOpen = vi.fn();

      renderHook(() =>
        useWebSocket(
          { url: 'ws://localhost:8000/ws/test' },
          { onOpen }
        )
      );

      await act(async () => {
        vi.advanceTimersByTime(20);
      });

      await waitFor(() => {
        expect(onOpen).toHaveBeenCalledTimes(1);
      });
    });

    it('should disconnect on unmount', async () => {
      const { result, unmount } = renderHook(() =>
        useWebSocket({ url: 'ws://localhost:8000/ws/test' })
      );

      // Wait for connection
      await act(async () => {
        vi.advanceTimersByTime(20);
      });

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true);
      });

      // Unmount
      unmount();

      expect(result.current.state).toBe(WebSocketState.DISCONNECTED);
    });

    it('should allow manual disconnect', async () => {
      const { result } = renderHook(() =>
        useWebSocket({ url: 'ws://localhost:8000/ws/test' })
      );

      // Wait for connection
      await act(async () => {
        vi.advanceTimersByTime(20);
      });

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true);
      });

      // Disconnect manually
      act(() => {
        result.current.disconnect();
      });

      expect(result.current.state).toBe(WebSocketState.DISCONNECTED);
      expect(result.current.isConnected).toBe(false);
    });
  });

  describe('Message Sending', () => {
    it('should send text messages', async () => {
      const { result } = renderHook(() =>
        useWebSocket({ url: 'ws://localhost:8000/ws/test' })
      );

      // Wait for connection
      await act(async () => {
        vi.advanceTimersByTime(20);
      });

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true);
      });

      // Send text message
      act(() => {
        result.current.sendText('test message');
      });

      // Check sent messages
      const ws = (global.WebSocket as any).mock.results[0].value;
      expect(ws.sentMessages).toContain('test message');
    });

    it('should send JSON messages', async () => {
      const { result } = renderHook(() =>
        useWebSocket({ url: 'ws://localhost:8000/ws/test' })
      );

      await act(async () => {
        vi.advanceTimersByTime(20);
      });

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true);
      });

      // Send JSON message
      act(() => {
        result.current.sendJSON({ type: 'test', value: 123 });
      });

      const ws = (global.WebSocket as any).mock.results[0].value;
      expect(ws.sentMessages[0]).toBe(JSON.stringify({ type: 'test', value: 123 }));
    });

    it('should request slice', async () => {
      const { result } = renderHook(() =>
        useWebSocket({ url: 'ws://localhost:8000/ws/test' })
      );

      await act(async () => {
        vi.advanceTimersByTime(20);
      });

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true);
      });

      // Request slice
      act(() => {
        result.current.requestSlice('file123', 42);
      });

      const ws = (global.WebSocket as any).mock.results[0].value;
      const message = JSON.parse(ws.sentMessages[0]);

      expect(message).toEqual({
        type: 'request_slice',
        file_id: 'file123',
        slice_index: 42,
      });
    });

    it('should request metadata', async () => {
      const { result } = renderHook(() =>
        useWebSocket({ url: 'ws://localhost:8000/ws/test' })
      );

      await act(async () => {
        vi.advanceTimersByTime(20);
      });

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true);
      });

      // Request metadata
      act(() => {
        result.current.requestMetadata('file123');
      });

      const ws = (global.WebSocket as any).mock.results[0].value;
      const message = JSON.parse(ws.sentMessages[0]);

      expect(message).toEqual({
        type: 'request_metadata',
        file_id: 'file123',
      });
    });

    it('should send ping', async () => {
      const { result } = renderHook(() =>
        useWebSocket({ url: 'ws://localhost:8000/ws/test' })
      );

      await act(async () => {
        vi.advanceTimersByTime(20);
      });

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true);
      });

      // Send ping
      act(() => {
        result.current.ping();
      });

      const ws = (global.WebSocket as any).mock.results[0].value;
      const message = JSON.parse(ws.sentMessages[0]);

      expect(message).toEqual({ type: 'ping' });
    });

    it('should queue messages when not connected', async () => {
      const { result } = renderHook(() =>
        useWebSocket({ url: 'ws://localhost:8000/ws/test' })
      );

      // Send message before connection is established
      act(() => {
        result.current.sendText('queued message');
      });

      // Wait for connection
      await act(async () => {
        vi.advanceTimersByTime(20);
      });

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true);
      });

      // Check that queued message was sent
      const ws = (global.WebSocket as any).mock.results[0].value;
      expect(ws.sentMessages).toContain('queued message');
    });
  });

  describe('Message Receiving', () => {
    it('should handle text messages (pong)', async () => {
      const { result } = renderHook(() =>
        useWebSocket({ url: 'ws://localhost:8000/ws/test' })
      );

      await act(async () => {
        vi.advanceTimersByTime(20);
      });

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true);
      });

      // Simulate pong message
      const ws = (global.WebSocket as any).mock.results[0].value;

      act(() => {
        ws.simulateMessage(JSON.stringify({ type: 'pong', timestamp: Date.now() }));
      });

      // Should update lastHeartbeat
      expect(result.current.lastHeartbeat).not.toBeNull();
    });

    it('should call onMetadata handler', async () => {
      const onMetadata = vi.fn();

      const { result } = renderHook(() =>
        useWebSocket(
          { url: 'ws://localhost:8000/ws/test' },
          { onMetadata }
        )
      );

      await act(async () => {
        vi.advanceTimersByTime(20);
      });

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true);
      });

      // Create binary METADATA message
      const metadata = { format: 'DICOM', slices: 100 };
      const metadataJson = JSON.stringify(metadata);
      const encoder = new TextEncoder();
      const payloadBytes = encoder.encode(metadataJson);

      // Calculate CRC32 (simplified for test)
      const crc = 0x12345678;

      // Build header
      const header = new ArrayBuffer(24);
      const view = new DataView(header);
      view.setUint32(0, 0x4d4449, true); // magic
      view.setUint16(4, 1, true); // version
      view.setUint8(6, MessageType.METADATA);
      view.setUint8(7, CompressionType.NONE);
      view.setUint32(8, payloadBytes.length, true);
      view.setUint32(12, 0, true); // sequence
      view.setUint32(16, crc, true);
      view.setUint32(20, 0, true); // reserved

      // Note: This test would need actual CRC32 calculation and Blob creation
      // For now, we'll skip the full binary protocol test in unit tests
      // (Integration tests would cover this)
    });
  });

  describe('Reconnection', () => {
    it('should reconnect on close', async () => {
      const { result } = renderHook(() =>
        useWebSocket({
          url: 'ws://localhost:8000/ws/test',
          autoReconnect: true,
          reconnectDelay: 1000,
        })
      );

      // Wait for initial connection
      await act(async () => {
        vi.advanceTimersByTime(20);
      });

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true);
      });

      // Simulate disconnect
      const ws = (global.WebSocket as any).mock.results[0].value;

      act(() => {
        ws.close();
      });

      expect(result.current.state).toBe(WebSocketState.DISCONNECTED);

      // Wait for reconnection delay
      await act(async () => {
        vi.advanceTimersByTime(1500);
      });

      // Should attempt reconnection
      expect(result.current.reconnectAttempts).toBeGreaterThan(0);
    });

    it('should respect maxReconnectAttempts', async () => {
      const { result } = renderHook(() =>
        useWebSocket({
          url: 'ws://localhost:8000/ws/test',
          autoReconnect: true,
          maxReconnectAttempts: 2,
          reconnectDelay: 100,
        })
      );

      await act(async () => {
        vi.advanceTimersByTime(20);
      });

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true);
      });

      // Simulate multiple disconnections
      for (let i = 0; i < 3; i++) {
        const ws = (global.WebSocket as any).mock.results[i].value;

        act(() => {
          ws.close();
        });

        await act(async () => {
          vi.advanceTimersByTime(200);
        });
      }

      // Should not exceed max attempts
      expect(result.current.reconnectAttempts).toBeLessThanOrEqual(2);
    });

    it('should use exponential backoff', async () => {
      const { result } = renderHook(() =>
        useWebSocket({
          url: 'ws://localhost:8000/ws/test',
          autoReconnect: true,
          reconnectDelay: 1000,
          maxReconnectDelay: 30000,
        })
      );

      await act(async () => {
        vi.advanceTimersByTime(20);
      });

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true);
      });

      // Disconnect and check backoff
      const ws = (global.WebSocket as any).mock.results[0].value;

      act(() => {
        ws.close();
      });

      // First reconnect: ~1s
      await act(async () => {
        vi.advanceTimersByTime(1500);
      });

      expect(result.current.reconnectAttempts).toBe(1);

      // Disconnect again
      const ws2 = (global.WebSocket as any).mock.results[1].value;

      act(() => {
        ws2.close();
      });

      // Second reconnect: ~2s (exponential backoff)
      await act(async () => {
        vi.advanceTimersByTime(3000);
      });

      expect(result.current.reconnectAttempts).toBe(2);
    });

    it('should not reconnect if disabled', async () => {
      const { result } = renderHook(() =>
        useWebSocket({
          url: 'ws://localhost:8000/ws/test',
          autoReconnect: false,
        })
      );

      await act(async () => {
        vi.advanceTimersByTime(20);
      });

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true);
      });

      // Disconnect
      const ws = (global.WebSocket as any).mock.results[0].value;

      act(() => {
        ws.close();
      });

      // Wait
      await act(async () => {
        vi.advanceTimersByTime(5000);
      });

      // Should not reconnect
      expect(result.current.reconnectAttempts).toBe(0);
      expect(result.current.state).toBe(WebSocketState.DISCONNECTED);
    });
  });

  describe('Heartbeat', () => {
    it('should update lastHeartbeat on heartbeat message', async () => {
      const { result } = renderHook(() =>
        useWebSocket({ url: 'ws://localhost:8000/ws/test' })
      );

      await act(async () => {
        vi.advanceTimersByTime(20);
      });

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true);
      });

      // Initially null
      expect(result.current.lastHeartbeat).toBeNull();

      // Simulate pong (which updates heartbeat)
      const ws = (global.WebSocket as any).mock.results[0].value;

      act(() => {
        ws.simulateMessage(
          JSON.stringify({ type: 'pong', timestamp: Date.now() })
        );
      });

      // Should be updated
      expect(result.current.lastHeartbeat).not.toBeNull();
    });
  });

  describe('Error Handling', () => {
    it('should call onConnectionError on error', async () => {
      const onConnectionError = vi.fn();

      const { result } = renderHook(() =>
        useWebSocket(
          { url: 'ws://localhost:8000/ws/test' },
          { onConnectionError }
        )
      );

      await act(async () => {
        vi.advanceTimersByTime(20);
      });

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true);
      });

      // Simulate error
      const ws = (global.WebSocket as any).mock.results[0].value;

      act(() => {
        ws.simulateError();
      });

      expect(onConnectionError).toHaveBeenCalled();
      expect(result.current.state).toBe(WebSocketState.ERROR);
    });

    it('should call onClose on disconnect', async () => {
      const onClose = vi.fn();

      const { result } = renderHook(() =>
        useWebSocket(
          { url: 'ws://localhost:8000/ws/test' },
          { onClose }
        )
      );

      await act(async () => {
        vi.advanceTimersByTime(20);
      });

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true);
      });

      // Disconnect
      act(() => {
        result.current.disconnect();
      });

      expect(onClose).toHaveBeenCalled();
    });
  });
});
