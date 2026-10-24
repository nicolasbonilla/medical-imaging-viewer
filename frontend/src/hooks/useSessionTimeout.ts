/**
 * useSessionTimeout - HIPAA Compliant Session Management Hook
 *
 * Implements automatic session timeout per HIPAA Security Rule requirements:
 * - § 164.312(a)(2)(iii): Automatic logoff after period of inactivity
 * - Standard timeout: 15 minutes for healthcare applications
 * - Warning displayed 2 minutes before logout
 *
 * Activity events that reset the timer:
 * - Mouse movement
 * - Keyboard input
 * - Touch events
 * - Scroll events
 * - Click events
 *
 * CAPA-015 review M2: activity is SHARED across the tabs of the app (localStorage key
 * `mstool_last_activity` + the `storage` event). Each tab used to run its own timer, so a tab left
 * in the background logged the user out — ending the session of the tab where they were working.
 * Now the warning and the log-off happen only when the user has been inactive in EVERY tab.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { ACTIVITY_KEY } from '@/services/session';

interface SessionTimeoutConfig {
  /** Session timeout duration in milliseconds (default: 15 minutes = 900000ms) */
  timeoutDuration?: number;
  /** Warning time before logout in milliseconds (default: 2 minutes = 120000ms) */
  warningDuration?: number;
  /** Callback when session is about to expire */
  onWarning?: (remainingSeconds: number) => void;
  /** Callback when session expires */
  onTimeout?: () => void;
  /** Whether the timeout is enabled (default: true) */
  enabled?: boolean;
}

interface SessionTimeoutState {
  /** Whether the warning modal should be shown */
  showWarning: boolean;
  /** Seconds remaining before logout */
  remainingSeconds: number;
  /** Reset the session timer (call on user activity) */
  resetTimer: () => void;
  /** Extend the session (user clicked "Stay Logged In") */
  extendSession: () => void;
  /** Whether the session is active */
  isActive: boolean;
  /** Last activity timestamp */
  lastActivity: Date;
}

// Default values based on HIPAA recommendations
const DEFAULT_TIMEOUT = 15 * 60 * 1000; // 15 minutes
const DEFAULT_WARNING = 2 * 60 * 1000; // 2 minutes before timeout

// Activity events to track
const ACTIVITY_EVENTS = [
  'mousedown',
  'mousemove',
  'keydown',
  'scroll',
  'touchstart',
  'click',
  'wheel',
] as const;

function readSharedActivity(): number {
  try {
    const v = Number(localStorage.getItem(ACTIVITY_KEY));
    return Number.isFinite(v) ? v : 0;
  } catch {
    return 0;
  }
}

export function useSessionTimeout({
  timeoutDuration = DEFAULT_TIMEOUT,
  warningDuration = DEFAULT_WARNING,
  onWarning,
  onTimeout,
  enabled = true,
}: SessionTimeoutConfig = {}): SessionTimeoutState {
  const [showWarning, setShowWarning] = useState(false);
  const [remainingSeconds, setRemainingSeconds] = useState(Math.floor(warningDuration / 1000));
  const [isActive, setIsActive] = useState(true);
  const [lastActivity, setLastActivity] = useState(new Date());

  // Refs to avoid stale closures
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);
  const warningTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const countdownRef = useRef<NodeJS.Timeout | null>(null);
  const lastActivityRef = useRef<number>(Date.now());
  const showWarningRef = useRef(false);
  const handleWarningRef = useRef<() => void>(() => undefined);
  const handleTimeoutRef = useRef<() => void>(() => undefined);

  /** The latest activity in ANY tab of the app. */
  const lastAnyTab = useCallback(() => Math.max(lastActivityRef.current, readSharedActivity()), []);

  // Clear all timers
  const clearAllTimers = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    if (warningTimeoutRef.current) {
      clearTimeout(warningTimeoutRef.current);
      warningTimeoutRef.current = null;
    }
    if (countdownRef.current) {
      clearInterval(countdownRef.current);
      countdownRef.current = null;
    }
  }, []);

  /** Schedule warning and log-off counted from `base` (the latest activity in any tab). */
  const scheduleFrom = useCallback((base: number) => {
    clearAllTimers();
    showWarningRef.current = false;
    setShowWarning(false);
    const now = Date.now();
    warningTimeoutRef.current = setTimeout(() => handleWarningRef.current(),
      Math.max(0, base + timeoutDuration - warningDuration - now));
    timeoutRef.current = setTimeout(() => handleTimeoutRef.current(), Math.max(0, base + timeoutDuration - now));
  }, [clearAllTimers, timeoutDuration, warningDuration]);

  // Handle session timeout
  const handleTimeout = useCallback(() => {
    const base = lastAnyTab();
    if (Date.now() - base < timeoutDuration) {   // the user is working in another tab
      scheduleFrom(base);
      return;
    }
    clearAllTimers();
    setIsActive(false);
    showWarningRef.current = false;
    setShowWarning(false);
    onTimeout?.();
  }, [clearAllTimers, lastAnyTab, onTimeout, scheduleFrom, timeoutDuration]);

  // Start countdown when warning is shown
  const startCountdown = useCallback(() => {
    let seconds = Math.floor(warningDuration / 1000);
    setRemainingSeconds(seconds);

    countdownRef.current = setInterval(() => {
      seconds -= 1;
      setRemainingSeconds(seconds);
      onWarning?.(seconds);

      if (seconds <= 0) {
        if (countdownRef.current) {
          clearInterval(countdownRef.current);
        }
        handleTimeoutRef.current();
      }
    }, 1000);
  }, [warningDuration, onWarning]);

  // Show warning before timeout
  const handleWarning = useCallback(() => {
    const base = lastAnyTab();
    if (Date.now() - base < timeoutDuration - warningDuration) {   // active in another tab
      scheduleFrom(base);
      return;
    }
    showWarningRef.current = true;
    setShowWarning(true);
    startCountdown();
  }, [lastAnyTab, scheduleFrom, startCountdown, timeoutDuration, warningDuration]);

  handleWarningRef.current = handleWarning;
  handleTimeoutRef.current = handleTimeout;

  // Reset the session timer (activity in THIS tab: shared with the other tabs)
  const resetTimer = useCallback(() => {
    if (!enabled) return;

    const now = Date.now();
    lastActivityRef.current = now;
    try { localStorage.setItem(ACTIVITY_KEY, String(now)); } catch { /* storage unavailable */ }
    setLastActivity(new Date(now));
    setIsActive(true);
    scheduleFrom(now);
  }, [enabled, scheduleFrom]);

  // Extend session (user acknowledged warning)
  const extendSession = useCallback(() => {
    setShowWarning(false);
    resetTimer();
  }, [resetTimer]);

  // Throttled activity handler
  const handleActivity = useCallback(() => {
    // Don't reset if warning is showing (user must click extend)
    if (showWarning) return;

    // Throttle: only reset if more than 1 second since last reset
    const now = Date.now();
    if (now - lastActivityRef.current < 1000) return;

    resetTimer();
  }, [showWarning, resetTimer]);

  // Setup activity listeners
  useEffect(() => {
    if (!enabled) {
      clearAllTimers();
      return;
    }

    // Add activity listeners
    ACTIVITY_EVENTS.forEach((event) => {
      document.addEventListener(event, handleActivity, { passive: true });
    });

    // Start initial timer
    resetTimer();

    // Cleanup
    return () => {
      ACTIVITY_EVENTS.forEach((event) => {
        document.removeEventListener(event, handleActivity);
      });
      clearAllTimers();
    };
  }, [enabled, handleActivity, resetTimer, clearAllTimers]);

  // Activity in another tab: hide this tab's warning and count from that activity
  useEffect(() => {
    if (!enabled) return undefined;
    const onStorage = (e: StorageEvent) => {
      if (e.key !== ACTIVITY_KEY) return;
      setIsActive(true);
      scheduleFrom(lastAnyTab());
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, [enabled, lastAnyTab, scheduleFrom]);

  // Handle visibility change (user switches tabs)
  useEffect(() => {
    if (!enabled) return;

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        // Check if session should have expired while tab was hidden (activity in any tab counts)
        const elapsed = Date.now() - lastAnyTab();
        if (elapsed >= timeoutDuration) {
          handleTimeout();
        } else if (elapsed >= timeoutDuration - warningDuration) {
          // Should show warning
          handleWarning();
        }
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [enabled, timeoutDuration, warningDuration, handleTimeout, handleWarning, lastAnyTab]);

  return {
    showWarning,
    remainingSeconds,
    resetTimer,
    extendSession,
    isActive,
    lastActivity,
  };
}

export default useSessionTimeout;
