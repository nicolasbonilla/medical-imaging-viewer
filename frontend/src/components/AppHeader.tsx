/**
 * AppHeader — persistent header bar + breadcrumb navigation.
 *
 * Design System compliance:
 * - App bar: h-[48px], bg-gray-900/90
 * - Breadcrumb: h-[36px], bg-gray-800/50
 * - All header controls: 36×36px (md button size), gap-4
 * - Border radius: 6px (radius-md)
 * - Typography: app name 14px/700, breadcrumb 12px/400
 *
 * @module components/AppHeader
 */

import { ChevronRight, Brain } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import ThemeToggle from './ThemeToggle';
import LanguageSelector from './LanguageSelector';
import UserMenu from './UserMenu';

export interface BreadcrumbItem {
  label: string;
  path?: string;
}

interface AppHeaderProps {
  title?: string;
  subtitle?: string;
  breadcrumbs?: BreadcrumbItem[];
  rightControls?: React.ReactNode;
  compact?: boolean;
  onBack?: () => void;
}

export default function AppHeader({
  breadcrumbs,
  rightControls,
  onBack,
}: AppHeaderProps) {
  const location = useLocation();
  const autoBreadcrumbs: BreadcrumbItem[] = breadcrumbs || (() => {
    const parts = location.pathname.split('/').filter(Boolean);
    const items: BreadcrumbItem[] = [];
    if (parts.length > 1) {
      items.push({ label: 'Home', path: '/app' });
    }
    return items;
  })();

  return (
    <header className="relative" style={{ zIndex: 200 }}>

      {/* ── LINE 1: App bar — 60px (12+36+12), padding 24px ── */}
      <div
        className="border-b border-gray-700"
        style={{
          height: 60,
          display: 'flex',
          alignItems: 'center',
          padding: '0 24px',
          background: '#111827',
        }}
      >
        {/* Left: Logo + name — gap 8px (4px grid) */}
        <Link
          to="/app"
          className="flex items-center no-underline"
          style={{ gap: 8 }}
          aria-label="MSTool-AI Home"
        >
          <div
            className="flex items-center justify-center bg-brand-950 border border-brand-500/30"
            style={{ width: 36, height: 36, borderRadius: 6 }}
          >
            <Brain style={{ width: 18, height: 18, color: 'white' }} />
          </div>
          <span style={{ fontSize: 14, fontWeight: 700, color: '#F9FAFB' }}>
            MSTool-AI
          </span>
        </Link>

        {/* Right: controls — ALL 36×36, gap 4px per Design System §2 */}
        <div
          className="ml-auto flex items-center"
          style={{ gap: 4 }}
        >
          {rightControls && (
            <>
              {rightControls}
              <div style={{ width: 1, height: 24, background: '#374151', margin: '0 8px' }} />
            </>
          )}
          <ThemeToggle variant="minimal" />
          <LanguageSelector variant="minimal" />
          <UserMenu />
        </div>
      </div>

      {/* ── LINE 2: Breadcrumb — 32px, padding 24px ── */}
      {autoBreadcrumbs.length > 0 && (
        <div
          className="border-b border-gray-700/30"
          style={{
            height: 32,
            display: 'flex',
            alignItems: 'center',
            padding: '0 24px',
            background: '#1a2332',
          }}
        >
          <nav aria-label="Breadcrumb" className="flex items-center" style={{ gap: 6 }}>
            {onBack && (
              <button
                onClick={onBack}
                className="text-gray-400 hover:text-gray-200 transition-colors"
                style={{ marginRight: 4, display: 'flex', alignItems: 'center' }}
                aria-label="Go back"
              >
                <ChevronRight style={{ width: 14, height: 14, transform: 'rotate(180deg)' }} />
              </button>
            )}
            {autoBreadcrumbs.map((item, i) => (
              <span key={i} className="flex items-center" style={{ gap: 6 }}>
                {i > 0 && (
                  <ChevronRight
                    style={{ width: 12, height: 12, color: '#4B5563', flexShrink: 0 }}
                  />
                )}
                {item.path ? (
                  <Link
                    to={item.path}
                    className="hover:text-blue-400 transition-colors"
                    style={{ fontSize: 12, fontWeight: 400, color: '#9CA3AF' }}
                  >
                    {item.label}
                  </Link>
                ) : (
                  <span
                    aria-current="page"
                    style={{ fontSize: 12, fontWeight: 500, color: '#E5E7EB' }}
                  >
                    {item.label}
                  </span>
                )}
              </span>
            ))}
          </nav>
        </div>
      )}
    </header>
  );
}
