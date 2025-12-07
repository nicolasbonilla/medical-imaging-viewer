/**
 * Feature Flags Configuration
 *
 * Controls which optimization features are enabled.
 * These flags allow for gradual rollout and easy rollback.
 */

export interface FeatureFlags {
  // FASE 2: Binary Protocol & WebSocket
  BINARY_PROTOCOL: boolean;
  WEBSOCKET: boolean;

  // FASE 1: Performance Optimizations
  PREFETCHING: boolean;
  THROTTLING: boolean;

  // FASE 3: Advanced Caching
  INDEXEDDB_CACHE: boolean;

  // Development/Debug
  DEBUG_PERFORMANCE: boolean;
}

/**
 * Get feature flag value from environment or use default
 */
function getFeatureFlag(key: string, defaultValue: boolean): boolean {
  const envValue = import.meta.env[`VITE_${key}`];
  if (envValue === undefined) return defaultValue;
  return envValue === 'true' || envValue === '1';
}

/**
 * Feature flags configuration
 *
 * Defaults are set for FASE 1 (Quick Wins) - safe, low-risk optimizations
 */
export const FEATURES: FeatureFlags = {
  // FASE 2: Disabled by default (requires backend WebSocket support)
  BINARY_PROTOCOL: getFeatureFlag('ENABLE_BINARY_PROTOCOL', false),
  WEBSOCKET: getFeatureFlag('ENABLE_WEBSOCKET', false),

  // FASE 1: Enabled by default (low risk, high impact)
  PREFETCHING: getFeatureFlag('ENABLE_PREFETCHING', true),
  THROTTLING: getFeatureFlag('ENABLE_THROTTLING', true),

  // FASE 3: Disabled by default (requires testing)
  INDEXEDDB_CACHE: getFeatureFlag('ENABLE_INDEXEDDB_CACHE', false),

  // Debug
  DEBUG_PERFORMANCE: getFeatureFlag('DEBUG_PERFORMANCE', false),
};

/**
 * Performance configuration
 */
export const PERFORMANCE_CONFIG = {
  // Throttling configuration
  THROTTLE_MS: 16, // 60 FPS (1000ms / 60 = 16.67ms)
  DEBOUNCE_MS: 300, // Standard debounce delay

  // Prefetching configuration
  PREFETCH_SLICES: 3, // Number of slices to prefetch ahead

  // IndexedDB configuration
  INDEXEDDB_MAX_SIZE_MB: 500, // Max cache size
  INDEXEDDB_TTL_MS: 30 * 60 * 1000, // 30 minutes

  // WebSocket configuration
  WS_RECONNECT_ATTEMPTS: 5,
  WS_RECONNECT_INTERVAL_MS: 3000,
};

/**
 * Log current feature flags (development only)
 */
if (import.meta.env.DEV) {
  console.group('🚀 Feature Flags');
  Object.entries(FEATURES).forEach(([key, value]) => {
    console.log(`${key}: ${value ? '✅' : '❌'}`);
  });
  console.groupEnd();
}
