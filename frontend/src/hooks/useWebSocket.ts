/**
 * WebSocket Hook for Real-Time Medical Image Streaming.
 *
 * Professional-grade React hook for WebSocket connection management with:
 * - Automatic reconnection with exponential backoff
 * - Binary protocol integration
 * - Connection state management
 * - Message queue for reliability
 * - Heartbeat monitoring
 * - Error handling and recovery
 *
 * @module hooks/useWebSocket
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import {
  BinaryDeserializer,
  MessageType,
  type DeserializedMessage,
  type SliceDataPayload,
  type MetadataPayload,
  type ErrorPayload,
  type HeartbeatPayload,
} from '../services/binaryProtocol';

/**
 * WebSocket connection state.
 */
export enum WebSocketState {
  DISCONNECTED = 'DISCONNECTED',
  CONNECTING = 'CONNECTING',
  CONNECTED = 'CONNECTED',
  RECONNECTING = 'RECONNECTING',
  ERROR = 'ERROR',
}

/**
 * WebSocket configuration options.
 */
export interface WebSocketOptions {
  /** WebSocket URL */
  url: string;

  /** Enable automatic reconnection */
  autoReconnect?: boolean;

  /** Maximum reconnection attempts (0 = infinite) */
  maxReconnectAttempts?: number;

  /** Initial reconnection delay in ms */
  reconnectDelay?: number;

  /** Maximum reconnection delay in ms */
  maxReconnectDelay?: number;

  /** Heartbeat timeout in ms (0 = disabled) */
  heartbeatTimeout?: number;

  /** Enable debug logging */
  debug?: boolean;
}

/**
 * Message handler callbacks.
 */
export interface WebSocketHandlers {
  /** Handle slice data */
  onSliceData?: (payload: SliceDataPayload) => void;

  /** Handle metadata */
  onMetadata?: (payload: MetadataPayload) => void;

  /** Handle error messages */
  onError?: (payload: ErrorPayload) => void;

  /** Handle heartbeat */
  onHeartbeat?: (payload: HeartbeatPayload) => void;

  /** Handle connection open */
  onOpen?: () => void;

  /** Handle connection close */
  onClose?: () => void;

  /** Handle connection error */
  onConnectionError?: (error: Event) => void;
}

/**
 * WebSocket hook return type.
 */
export interface UseWebSocketReturn {
  /** Current connection state */
  state: WebSocketState;

  /** Is connected */
  isConnected: boolean;

  /** Is connecting */
  isConnecting: boolean;

  /** Send text message */
  sendText: (message: string) => void;

  /** Send JSON message */
  sendJSON: (data: Record<string, any>) => void;

  /** Request a slice */
  requestSlice: (fileId: string, sliceIndex: number) => void;

  /** Request metadata */
  requestMetadata: (fileId: string) => void;

  /** Send ping */
  ping: () => void;

  /** Manually connect */
  connect: () => void;

  /** Manually disconnect */
  disconnect: () => void;

  /** Reconnection attempts count */
  reconnectAttempts: number;

  /** Last heartbeat timestamp */
  lastHeartbeat: number | null;
}

/**
 * Default WebSocket options.
 */
const DEFAULT_OPTIONS: Required<Omit<WebSocketOptions, 'url'>> = {
  autoReconnect: true,
  maxReconnectAttempts: 10,
  reconnectDelay: 1000,
  maxReconnectDelay: 30000,
  heartbeatTimeout: 90000, // 90s (matches backend)
  debug: false,
};

/**
 * Custom hook for WebSocket connection with binary protocol support.
 *
 * @param options - WebSocket configuration
 * @param handlers - Message handlers
 * @returns WebSocket interface
 *
 * @example
 * ```tsx
 * const { state, isConnected, requestSlice } = useWebSocket(
 *   {
 *     url: 'ws://localhost:8000/api/v1/ws/imaging',
 *     autoReconnect: true,
 *   },
 *   {
 *     onSliceData: (payload) => {
 *       console.log('Received slice:', payload.sliceIndex);
 *       renderSlice(payload.data, payload.width, payload.height);
 *     },
 *     onError: (error) => {
 *       console.error('Error:', error.message);
 *     },
 *   }
 * );
 *
 * // Request a slice
 * const handleRequestSlice = () => {
 *   requestSlice('file123', 42);
 * };
 * ```
 */
export function useWebSocket(
  options: WebSocketOptions,
  handlers: WebSocketHandlers = {}
): UseWebSocketReturn {
  const config = { ...DEFAULT_OPTIONS, ...options };

  // State
  const [state, setState] = useState<WebSocketState>(WebSocketState.DISCONNECTED);
  const [reconnectAttempts, setReconnectAttempts] = useState(0);
  const [lastHeartbeat, setLastHeartbeat] = useState<number | null>(null);

  // Refs (persist across re-renders)
  const wsRef = useRef<WebSocket | null>(null);
  const deserializerRef = useRef<BinaryDeserializer>(new BinaryDeserializer());
  const reconnectTimeoutRef = useRef<number | null>(null);
  const heartbeatTimeoutRef = useRef<number | null>(null);
  const messageQueueRef = useRef<string[]>([]);
  const shouldReconnectRef = useRef(true);

  /**
   * Log debug message.
   */
  const log = useCallback(
    (message: string, ...args: any[]) => {
      if (config.debug) {
        console.log(`[useWebSocket] ${message}`, ...args);
      }
    },
    [config.debug]
  );

  /**
   * Clear reconnection timeout.
   */
  const clearReconnectTimeout = useCallback(() => {
    if (reconnectTimeoutRef.current !== null) {
      window.clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
  }, []);

  /**
   * Clear heartbeat timeout.
   */
  const clearHeartbeatTimeout = useCallback(() => {
    if (heartbeatTimeoutRef.current !== null) {
      window.clearTimeout(heartbeatTimeoutRef.current);
      heartbeatTimeoutRef.current = null;
    }
  }, []);

  /**
   * Reset heartbeat timeout.
   */
  const resetHeartbeatTimeout = useCallback(() => {
    clearHeartbeatTimeout();

    if (config.heartbeatTimeout > 0) {
      heartbeatTimeoutRef.current = window.setTimeout(() => {
        log('Heartbeat timeout - connection may be stale');

        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          // Close and trigger reconnection
          wsRef.current.close();
        }
      }, config.heartbeatTimeout);
    }
  }, [config.heartbeatTimeout, clearHeartbeatTimeout, log]);

  /**
   * Handle binary message from server.
   */
  const handleBinaryMessage = useCallback(
    async (data: Blob) => {
      try {
        const arrayBuffer = await data.arrayBuffer();
        const message: DeserializedMessage =
          deserializerRef.current.deserialize(arrayBuffer);

        log('Received message:', MessageType[message.header.messageType]);

        // Route message based on type
        switch (message.header.messageType) {
          case MessageType.SLICE_DATA:
            handlers.onSliceData?.(message.payload as SliceDataPayload);
            break;

          case MessageType.METADATA:
            handlers.onMetadata?.(message.payload as MetadataPayload);
            break;

          case MessageType.ERROR:
            handlers.onError?.(message.payload as ErrorPayload);
            break;

          case MessageType.HEARTBEAT:
            const heartbeat = message.payload as HeartbeatPayload;
            setLastHeartbeat(heartbeat.timestamp);
            resetHeartbeatTimeout();
            handlers.onHeartbeat?.(heartbeat);
            break;

          default:
            log('Unknown message type:', message.header.messageType);
        }
      } catch (error) {
        console.error('[useWebSocket] Failed to deserialize message:', error);
      }
    },
    [handlers, log, resetHeartbeatTimeout]
  );

  /**
   * Handle text message from server (e.g., pong).
   */
  const handleTextMessage = useCallback(
    (data: string) => {
      try {
        const message = JSON.parse(data);
        log('Received text message:', message.type);

        if (message.type === 'pong') {
          setLastHeartbeat(Date.now());
          resetHeartbeatTimeout();
        }
      } catch (error) {
        console.error('[useWebSocket] Failed to parse text message:', error);
      }
    },
    [log, resetHeartbeatTimeout]
  );

  /**
   * Send text message.
   */
  const sendText = useCallback(
    (message: string) => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(message);
        log('Sent text:', message);
      } else {
        // Queue message for later
        messageQueueRef.current.push(message);
        log('Queued message (not connected)');
      }
    },
    [log]
  );

  /**
   * Send JSON message.
   */
  const sendJSON = useCallback(
    (data: Record<string, any>) => {
      sendText(JSON.stringify(data));
    },
    [sendText]
  );

  /**
   * Request a slice.
   */
  const requestSlice = useCallback(
    (fileId: string, sliceIndex: number) => {
      sendJSON({
        type: 'request_slice',
        file_id: fileId,
        slice_index: sliceIndex,
      });
    },
    [sendJSON]
  );

  /**
   * Request metadata.
   */
  const requestMetadata = useCallback(
    (fileId: string) => {
      sendJSON({
        type: 'request_metadata',
        file_id: fileId,
      });
    },
    [sendJSON]
  );

  /**
   * Send ping.
   */
  const ping = useCallback(() => {
    sendJSON({ type: 'ping' });
  }, [sendJSON]);

  /**
   * Flush message queue.
   */
  const flushMessageQueue = useCallback(() => {
    while (messageQueueRef.current.length > 0) {
      const message = messageQueueRef.current.shift();
      if (message) {
        sendText(message);
      }
    }
  }, [sendText]);

  /**
   * Calculate reconnection delay with exponential backoff.
   */
  const getReconnectDelay = useCallback(
    (attempt: number): number => {
      const delay = Math.min(
        config.reconnectDelay * Math.pow(2, attempt),
        config.maxReconnectDelay
      );
      // Add jitter (±25%)
      const jitter = delay * (0.75 + Math.random() * 0.5);
      return jitter;
    },
    [config.reconnectDelay, config.maxReconnectDelay]
  );

  /**
   * Connect to WebSocket server.
   */
  const connect = useCallback(() => {
    // Prevent multiple connections
    if (
      wsRef.current &&
      (wsRef.current.readyState === WebSocket.CONNECTING ||
        wsRef.current.readyState === WebSocket.OPEN)
    ) {
      log('Already connected or connecting');
      return;
    }

    log('Connecting to:', config.url);
    setState(
      reconnectAttempts > 0
        ? WebSocketState.RECONNECTING
        : WebSocketState.CONNECTING
    );

    try {
      const ws = new WebSocket(config.url);
      ws.binaryType = 'blob'; // Receive binary data as Blob

      ws.onopen = () => {
        log('Connected');
        setState(WebSocketState.CONNECTED);
        setReconnectAttempts(0);
        shouldReconnectRef.current = true;

        // Reset heartbeat timeout
        resetHeartbeatTimeout();

        // Flush queued messages
        flushMessageQueue();

        handlers.onOpen?.();
      };

      ws.onmessage = (event) => {
        if (event.data instanceof Blob) {
          handleBinaryMessage(event.data);
        } else if (typeof event.data === 'string') {
          handleTextMessage(event.data);
        }
      };

      ws.onerror = (error) => {
        log('Connection error:', error);
        setState(WebSocketState.ERROR);
        handlers.onConnectionError?.(error);
      };

      ws.onclose = (event) => {
        log('Connection closed:', event.code, event.reason);
        setState(WebSocketState.DISCONNECTED);

        clearHeartbeatTimeout();
        handlers.onClose?.();

        // Attempt reconnection
        if (
          shouldReconnectRef.current &&
          config.autoReconnect &&
          (config.maxReconnectAttempts === 0 ||
            reconnectAttempts < config.maxReconnectAttempts)
        ) {
          const delay = getReconnectDelay(reconnectAttempts);
          log(`Reconnecting in ${delay.toFixed(0)}ms (attempt ${reconnectAttempts + 1})`);

          reconnectTimeoutRef.current = window.setTimeout(() => {
            setReconnectAttempts((prev) => prev + 1);
            connect();
          }, delay);
        } else {
          log('Not reconnecting');
        }
      };

      wsRef.current = ws;
    } catch (error) {
      console.error('[useWebSocket] Failed to create WebSocket:', error);
      setState(WebSocketState.ERROR);
    }
  }, [
    config.url,
    config.autoReconnect,
    config.maxReconnectAttempts,
    reconnectAttempts,
    log,
    resetHeartbeatTimeout,
    clearHeartbeatTimeout,
    flushMessageQueue,
    getReconnectDelay,
    handlers,
    handleBinaryMessage,
    handleTextMessage,
  ]);

  /**
   * Disconnect from WebSocket server.
   */
  const disconnect = useCallback(() => {
    log('Disconnecting');
    shouldReconnectRef.current = false;

    clearReconnectTimeout();
    clearHeartbeatTimeout();

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    setState(WebSocketState.DISCONNECTED);
    setReconnectAttempts(0);
  }, [log, clearReconnectTimeout, clearHeartbeatTimeout]);

  /**
   * Auto-connect on mount if URL is provided.
   */
  useEffect(() => {
    if (config.url) {
      connect();
    }

    // Cleanup on unmount
    return () => {
      disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config.url]);

  return {
    state,
    isConnected: state === WebSocketState.CONNECTED,
    isConnecting:
      state === WebSocketState.CONNECTING ||
      state === WebSocketState.RECONNECTING,
    sendText,
    sendJSON,
    requestSlice,
    requestMetadata,
    ping,
    connect,
    disconnect,
    reconnectAttempts,
    lastHeartbeat,
  };
}
