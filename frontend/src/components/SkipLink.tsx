/**
 * SkipLink - Accessibility Skip Navigation Component
 *
 * Implements WCAG 2.4.1: Bypass Blocks
 * Allows keyboard users to skip repetitive navigation content.
 *
 * Usage:
 * - Place at the very beginning of the page
 * - Links to main content area via ID
 * - Only visible when focused (keyboard navigation)
 */

import { useTranslation } from 'react-i18next';
import { handleSkipLink } from '@/utils/accessibility';

interface SkipLinkProps {
  /** ID of the main content element to skip to */
  mainContentId?: string;
  /** Additional skip link targets */
  additionalLinks?: Array<{
    targetId: string;
    label: string;
  }>;
}

export function SkipLink({
  mainContentId = 'main-content',
  additionalLinks = [],
}: SkipLinkProps) {
  const { t } = useTranslation();

  const handleClick = (e: React.MouseEvent<HTMLAnchorElement>, targetId: string) => {
    e.preventDefault();
    handleSkipLink(targetId);
  };

  // Styles: visually hidden until focused
  const linkStyles = `
    sr-only
    focus:not-sr-only
    focus:absolute
    focus:top-4
    focus:left-4
    focus:z-[9999]
    focus:px-4
    focus:py-2
    focus:bg-primary-600
    focus:text-white
    focus:font-medium
    focus:text-sm
    focus:rounded-lg
    focus:shadow-lg
    focus:outline-none
    focus:ring-2
    focus:ring-offset-2
    focus:ring-primary-500
  `;

  return (
    <nav
      aria-label={t('accessibility.skipNavigation', 'Skip navigation')}
      className="contents"
    >
      <a
        href={`#${mainContentId}`}
        onClick={(e) => handleClick(e, mainContentId)}
        className={linkStyles}
      >
        {t('accessibility.skipToMain', 'Skip to main content')}
      </a>

      {additionalLinks.map((link) => (
        <a
          key={link.targetId}
          href={`#${link.targetId}`}
          onClick={(e) => handleClick(e, link.targetId)}
          className={linkStyles}
        >
          {link.label}
        </a>
      ))}
    </nav>
  );
}

export default SkipLink;
