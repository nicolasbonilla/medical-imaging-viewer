/**
 * Feature Flags Configuration
 *
 * Controls which optimization features are enabled.
 * These flags allow for gradual rollout and easy rollback.
 */

export interface FeatureFlags {
  // CLASS C CHANGE PROPOSAL CP-SLICE-THICKNESS-001 (DRAFT, PENDING owner approval; RC-058):
  // "reliability by slice thickness" card next to the lesion results (Paper A v0.3, PR #54).
  // OFF unless VITE_ENABLE_SLICE_THICKNESS_RELIABILITY is 'true' or '1'.
  SLICE_THICKNESS_RELIABILITY: boolean;

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

  // PROTOTYPE (IEC 62304 Class C change proposal, docs/research/flames-in-browser/):
  // FLAMeS MS-lesion segmentation running inside the browser. OFF unless VITE_ENABLE_BROWSER_FLAMES=true.
  BROWSER_FLAMES: boolean;

  // PRB-009: in-browser "Quick Screen" (normal / abnormal of one slice). Its model file
  // (/models/brain_screening.onnx) is NOT shipped with the app, so the feature is OFF unless
  // VITE_ENABLE_QUICK_SCREEN is 'true' or '1'; with it off the viewer neither shows it nor
  // requests the model.
  QUICK_SCREEN: boolean;
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
  // Class C draft (RC-058) — must stay OFF in production until the change is approved
  SLICE_THICKNESS_RELIABILITY: getFeatureFlag('ENABLE_SLICE_THICKNESS_RELIABILITY', false),

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

  // Prototype — must stay OFF in production until the Class C change is approved
  BROWSER_FLAMES: getFeatureFlag('ENABLE_BROWSER_FLAMES', false),

  // PRB-009 — OFF: the screening model is not part of the app
  QUICK_SCREEN: getFeatureFlag('ENABLE_QUICK_SCREEN', false),
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
