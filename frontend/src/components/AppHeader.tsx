/**
 * AppHeader — persistent header bar + breadcrumb navigation.
 *
 * Implements the three-tier medical imaging standard:
 * 1) Top bar: App name (always visible) + user controls (right)
 * 2) Breadcrumb: Home > Patient > Study > Current View
 * 3) Page title: shown below breadcrumb
 *
 * References:
 * - NNGroup breadcrumb guidelines (11 rules)
 * - WCAG 2.4.8 (Location) + aria-current="page"
 * - OHIF Viewer / Philips IntelliSpace "Control Strip" pattern
 * - Epic patient banner persistent context
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
  path?: string; // undefined = current page (not clickable)
}

interface AppHeaderProps {
  /** Page title shown below breadcrumb */
  title: string;
  /** Optional subtitle (e.g., study description) */
  subtitle?: string;
  /** Breadcrumb items — last item is current page (auto-marked) */
  breadcrumbs?: BreadcrumbItem[];
  /** Extra controls to show on the right (before user menu) */
  rightControls?: React.ReactNode;
  /** If true, show a compact header (for the viewer) */
  compact?: boolean;
  /** Optional back button handler (shows ← arrow) */
  onBack?: () => void;
}

export default function AppHeader({
  title,
  subtitle,
  breadcrumbs,
  rightControls,
  compact = false,
  onBack,
}: AppHeaderProps) {
  // Auto-generate breadcrumb from current URL if none provided
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
    <header className="relative z-20 backdrop-blur-xl bg-white/70 dark:bg-gray-900/80 border-b border-gray-200/50 dark:border-gray-700/50">
      <div className={`px-5 ${compact ? 'py-2.5' : 'py-3'}`}>
        <div className="flex items-center justify-between gap-4">

          {/* Left: Back + Logo + Title + Breadcrumb */}
          <div className="flex items-center gap-3 min-w-0">
            {/* Back button */}
            {onBack && (
              <button onClick={onBack}
                className="p-1.5 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors shrink-0"
                aria-label="Go back">
                <ChevronRight className="w-4 h-4 text-gray-500 rotate-180" />
              </button>
            )}

            {/* App logo — always visible, always same position */}
            <Link to="/app" className="shrink-0 flex items-center gap-2.5 group" aria-label="MSTool-AI Home">
              <div className="bg-gradient-to-br from-blue-500 to-purple-600 p-2 rounded-xl shadow-md group-hover:shadow-lg transition-shadow">
                <Brain className="w-5 h-5 text-white" />
              </div>
              <div className="hidden sm:block">
                <span className="text-sm font-bold text-gray-800 dark:text-white leading-none">MSTool-AI</span>
              </div>
            </Link>

            {/* Separator */}
            <div className="w-px h-8 bg-gray-200 dark:bg-gray-700 shrink-0" />

            {/* Breadcrumb + Title */}
            <div className="min-w-0">
              {/* Breadcrumb trail */}
              {autoBreadcrumbs.length > 0 && (
                <nav aria-label="Breadcrumb" className="flex items-center gap-1 text-[11px] mb-0.5">
                  {autoBreadcrumbs.map((item, i) => (
                    <span key={i} className="flex items-center gap-1">
                      {i > 0 && <ChevronRight className="w-3 h-3 text-gray-400 dark:text-gray-600 shrink-0" />}
                      {item.path ? (
                        <Link to={item.path}
                          className="text-gray-500 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors truncate max-w-[120px]">
                          {item.label}
                        </Link>
                      ) : (
                        <span className="text-gray-700 dark:text-gray-300 font-medium truncate max-w-[200px]"
                          aria-current="page">
                          {item.label}
                        </span>
                      )}
                    </span>
                  ))}
                </nav>
              )}

              {/* Page title */}
              <h1 className={`font-bold text-gray-900 dark:text-white leading-tight truncate ${compact ? 'text-base' : 'text-lg'}`}>
                {title}
              </h1>
              {subtitle && (
                <p className="text-xs text-gray-500 dark:text-gray-400 truncate mt-0.5">
                  {subtitle}
                </p>
              )}
            </div>
          </div>

          {/* Right: Custom controls + standard controls */}
          <div className="flex items-center gap-2 shrink-0">
            {rightControls}
            <ThemeToggle variant="minimal" />
            <LanguageSelector variant="minimal" />
            <UserMenu />
          </div>
        </div>
      </div>
    </header>
  );
}
