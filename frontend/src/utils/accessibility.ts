/**
 * Accessibility Utilities - WCAG 2.1 AA Compliance
 *
 * Implements core accessibility features for healthcare applications:
 * - Focus management for modals and dialogs
 * - Screen reader announcements
 * - Keyboard navigation helpers
 * - Skip links and focus traps
 *
 * References:
 * - WCAG 2.1 Success Criteria Level AA
 * - Section 508 of the Rehabilitation Act
 * - WAI-ARIA 1.2 Specification
 * - HIPAA §164.312(d) - Accessible health information
 */

/**
 * Creates a focus trap within a container element
 * Used for modals, dialogs, and dropdown menus
 *
 * WCAG 2.4.3: Focus Order
 */
export function createFocusTrap(container: HTMLElement): () => void {
  const focusableSelectors = [
    'a[href]',
    'button:not([disabled])',
    'input:not([disabled])',
    'select:not([disabled])',
    'textarea:not([disabled])',
    '[tabindex]:not([tabindex="-1"])',
    '[contenteditable="true"]',
  ].join(', ');

  const focusableElements = container.querySelectorAll<HTMLElement>(focusableSelectors);
  const firstElement = focusableElements[0];
  const lastElement = focusableElements[focusableElements.length - 1];

  const handleKeyDown = (event: KeyboardEvent) => {
    if (event.key !== 'Tab') return;

    if (event.shiftKey) {
      // Shift + Tab
      if (document.activeElement === firstElement) {
        event.preventDefault();
        lastElement?.focus();
      }
    } else {
      // Tab
      if (document.activeElement === lastElement) {
        event.preventDefault();
        firstElement?.focus();
      }
    }
  };

  container.addEventListener('keydown', handleKeyDown);

  // Focus the first element
  firstElement?.focus();

  // Return cleanup function
  return () => {
    container.removeEventListener('keydown', handleKeyDown);
  };
}

/**
 * Announces a message to screen readers using aria-live regions
 *
 * WCAG 4.1.3: Status Messages
 */
export function announceToScreenReader(
  message: string,
  priority: 'polite' | 'assertive' = 'polite'
): void {
  // Find or create the announcement region
  let region = document.getElementById(`sr-announcement-${priority}`);

  if (!region) {
    region = document.createElement('div');
    region.id = `sr-announcement-${priority}`;
    region.setAttribute('role', 'status');
    region.setAttribute('aria-live', priority);
    region.setAttribute('aria-atomic', 'true');
    region.className = 'sr-only';
    // Visually hidden but accessible to screen readers
    region.style.cssText = `
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    `;
    document.body.appendChild(region);
  }

  // Clear and set new message (needed for repeated announcements)
  region.textContent = '';
  setTimeout(() => {
    region!.textContent = message;
  }, 100);
}

/**
 * Generates unique IDs for ARIA relationships
 *
 * WCAG 4.1.2: Name, Role, Value
 */
let idCounter = 0;
export function generateAriaId(prefix: string = 'aria'): string {
  idCounter += 1;
  return `${prefix}-${idCounter}`;
}

/**
 * Keyboard navigation handler for list/grid components
 *
 * WCAG 2.1.1: Keyboard
 */
export type KeyboardNavigationOptions = {
  items: HTMLElement[];
  currentIndex: number;
  onSelect?: (index: number) => void;
  onEscape?: () => void;
  orientation?: 'horizontal' | 'vertical' | 'both';
  loop?: boolean;
};

export function handleKeyboardNavigation(
  event: KeyboardEvent,
  options: KeyboardNavigationOptions
): number {
  const { items, currentIndex, onSelect, onEscape, orientation = 'vertical', loop = true } = options;

  let newIndex = currentIndex;
  const itemCount = items.length;

  switch (event.key) {
    case 'ArrowDown':
      if (orientation === 'vertical' || orientation === 'both') {
        event.preventDefault();
        newIndex = loop
          ? (currentIndex + 1) % itemCount
          : Math.min(currentIndex + 1, itemCount - 1);
      }
      break;

    case 'ArrowUp':
      if (orientation === 'vertical' || orientation === 'both') {
        event.preventDefault();
        newIndex = loop
          ? (currentIndex - 1 + itemCount) % itemCount
          : Math.max(currentIndex - 1, 0);
      }
      break;

    case 'ArrowRight':
      if (orientation === 'horizontal' || orientation === 'both') {
        event.preventDefault();
        newIndex = loop
          ? (currentIndex + 1) % itemCount
          : Math.min(currentIndex + 1, itemCount - 1);
      }
      break;

    case 'ArrowLeft':
      if (orientation === 'horizontal' || orientation === 'both') {
        event.preventDefault();
        newIndex = loop
          ? (currentIndex - 1 + itemCount) % itemCount
          : Math.max(currentIndex - 1, 0);
      }
      break;

    case 'Home':
      event.preventDefault();
      newIndex = 0;
      break;

    case 'End':
      event.preventDefault();
      newIndex = itemCount - 1;
      break;

    case 'Enter':
    case ' ':
      event.preventDefault();
      onSelect?.(currentIndex);
      break;

    case 'Escape':
      event.preventDefault();
      onEscape?.();
      break;
  }

  if (newIndex !== currentIndex && items[newIndex]) {
    items[newIndex].focus();
  }

  return newIndex;
}

/**
 * Focus visible polyfill helper
 * Adds data attribute to distinguish keyboard vs mouse focus
 *
 * WCAG 2.4.7: Focus Visible
 */
export function initializeFocusVisible(): void {
  let hadKeyboardEvent = false;

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Tab' || e.key === 'Escape') {
      hadKeyboardEvent = true;
    }
  });

  document.addEventListener('mousedown', () => {
    hadKeyboardEvent = false;
  });

  document.addEventListener(
    'focus',
    (e) => {
      const target = e.target as HTMLElement;
      if (hadKeyboardEvent && target) {
        target.setAttribute('data-focus-visible', 'true');
      }
    },
    true
  );

  document.addEventListener(
    'blur',
    (e) => {
      const target = e.target as HTMLElement;
      if (target) {
        target.removeAttribute('data-focus-visible');
      }
    },
    true
  );
}

/**
 * Validates color contrast ratio for WCAG AA compliance
 *
 * WCAG 1.4.3: Contrast (Minimum) - 4.5:1 for normal text, 3:1 for large text
 */
export function getContrastRatio(foreground: string, background: string): number {
  const getLuminance = (hexColor: string): number => {
    // Remove # if present
    const hex = hexColor.replace('#', '');
    const r = parseInt(hex.slice(0, 2), 16) / 255;
    const g = parseInt(hex.slice(2, 4), 16) / 255;
    const b = parseInt(hex.slice(4, 6), 16) / 255;

    const toLinear = (c: number) =>
      c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);

    return 0.2126 * toLinear(r) + 0.7152 * toLinear(g) + 0.0722 * toLinear(b);
  };

  const l1 = getLuminance(foreground);
  const l2 = getLuminance(background);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);

  return (lighter + 0.05) / (darker + 0.05);
}

export function meetsContrastRequirement(
  foreground: string,
  background: string,
  isLargeText: boolean = false
): boolean {
  const ratio = getContrastRatio(foreground, background);
  return isLargeText ? ratio >= 3 : ratio >= 4.5;
}

/**
 * Reduced motion preference detection
 *
 * WCAG 2.3.3: Animation from Interactions
 */
export function prefersReducedMotion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/**
 * ARIA live region component helper
 * Returns props for creating accessible status regions
 */
export function getAriaLiveProps(priority: 'polite' | 'assertive' = 'polite') {
  return {
    role: 'status',
    'aria-live': priority,
    'aria-atomic': true,
  };
}

/**
 * Skip link management for page navigation
 *
 * WCAG 2.4.1: Bypass Blocks
 */
export function handleSkipLink(targetId: string): void {
  const target = document.getElementById(targetId);
  if (target) {
    target.setAttribute('tabindex', '-1');
    target.focus();
    // Remove tabindex after focus to prevent tab stop
    target.addEventListener(
      'blur',
      () => {
        target.removeAttribute('tabindex');
      },
      { once: true }
    );
  }
}

/**
 * Medical alert accessibility helper
 * Ensures critical alerts are properly announced
 *
 * For patient safety alerts, allergies, critical values
 */
export function announceCriticalAlert(message: string): void {
  announceToScreenReader(message, 'assertive');

  // Also add to page's critical alerts region if it exists
  const alertsRegion = document.getElementById('critical-alerts-region');
  if (alertsRegion) {
    const alert = document.createElement('div');
    alert.setAttribute('role', 'alert');
    alert.textContent = message;
    alertsRegion.appendChild(alert);

    // Remove after announcement (5 seconds)
    setTimeout(() => {
      alert.remove();
    }, 5000);
  }
}
