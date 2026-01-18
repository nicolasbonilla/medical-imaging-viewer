/**
 * LiveRegion - Accessible Announcement Component
 *
 * Implements WCAG 4.1.3: Status Messages
 * Provides screen reader announcements without moving focus.
 *
 * Usage:
 * - For status updates (loading states, form validation)
 * - For success/error messages
 * - For dynamic content changes
 *
 * Priority levels:
 * - polite: Waits for user to finish current task (default)
 * - assertive: Interrupts immediately (use sparingly, for critical alerts)
 */

import { useEffect, useRef, useState } from 'react';

interface LiveRegionProps {
  /** The message to announce */
  message: string;
  /** Priority level for the announcement */
  priority?: 'polite' | 'assertive';
  /** Role attribute (status, alert, log) */
  role?: 'status' | 'alert' | 'log';
  /** Whether to clear the message after announcement */
  clearAfter?: number;
  /** Visual visibility (usually hidden for screen readers only) */
  visible?: boolean;
  /** Additional className for visible regions */
  className?: string;
}

export function LiveRegion({
  message,
  priority = 'polite',
  role = 'status',
  clearAfter,
  visible = false,
  className = '',
}: LiveRegionProps) {
  const [currentMessage, setCurrentMessage] = useState('');
  const timeoutRef = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    // Clear previous message first for repeated announcements
    setCurrentMessage('');

    // Set new message after brief delay
    const setMessageTimeout = setTimeout(() => {
      setCurrentMessage(message);
    }, 100);

    // Optional auto-clear
    if (clearAfter && message) {
      timeoutRef.current = setTimeout(() => {
        setCurrentMessage('');
      }, clearAfter);
    }

    return () => {
      clearTimeout(setMessageTimeout);
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, [message, clearAfter]);

  const baseStyles = visible
    ? className
    : 'absolute w-px h-px p-0 -m-px overflow-hidden whitespace-nowrap border-0';

  return (
    <div
      role={role}
      aria-live={priority}
      aria-atomic="true"
      className={baseStyles}
      style={visible ? undefined : { clip: 'rect(0, 0, 0, 0)' }}
    >
      {currentMessage}
    </div>
  );
}

/**
 * Hook for programmatic announcements
 */
export function useAnnounce() {
  const [announcement, setAnnouncement] = useState<{
    message: string;
    priority: 'polite' | 'assertive';
  } | null>(null);

  const announce = (message: string, priority: 'polite' | 'assertive' = 'polite') => {
    setAnnouncement({ message, priority });
  };

  const clear = () => {
    setAnnouncement(null);
  };

  return { announcement, announce, clear };
}

export default LiveRegion;
