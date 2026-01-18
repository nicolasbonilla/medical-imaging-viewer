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
 */

import { useState, useEffect, useCallback, useRef } from 'react';

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

  // Handle session timeout
  const handleTimeout = useCallback(() => {
    clearAllTimers();
    setIsActive(false);
    setShowWarning(false);
    onTimeout?.();
  }, [clearAllTimers, onTimeout]);

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
        handleTimeout();
      }
    }, 1000);
  }, [warningDuration, onWarning, handleTimeout]);

  // Show warning before timeout
  const handleWarning = useCallback(() => {
    setShowWarning(true);
    startCountdown();
  }, [startCountdown]);

  // Reset the session timer
  const resetTimer = useCallback(() => {
    if (!enabled) return;

    lastActivityRef.current = Date.now();
    setLastActivity(new Date());
    setShowWarning(false);
    setIsActive(true);
    clearAllTimers();

    // Set warning timer (fires before timeout)
    warningTimeoutRef.current = setTimeout(() => {
      handleWarning();
    }, timeoutDuration - warningDuration);

    // Set final timeout (backup in case warning countdown fails)
    timeoutRef.current = setTimeout(() => {
      handleTimeout();
    }, timeoutDuration);
  }, [enabled, timeoutDuration, warningDuration, clearAllTimers, handleWarning, handleTimeout]);

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

  // Handle visibility change (user switches tabs)
  useEffect(() => {
    if (!enabled) return;

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        // Check if session should have expired while tab was hidden
        const elapsed = Date.now() - lastActivityRef.current;
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
  }, [enabled, timeoutDuration, warningDuration, handleTimeout, handleWarning]);

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
