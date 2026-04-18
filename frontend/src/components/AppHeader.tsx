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
  /** Page title (optional — breadcrumb last item serves as location) */
  title?: string;
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
    <header className="relative z-20">
      {/* LINE 1: App identity bar — fixed layout, always same structure */}
      <div className="backdrop-blur-xl bg-white/80 dark:bg-gray-900/90 border-b border-gray-200/50 dark:border-gray-700/50 px-5 h-12 flex items-center">
        <div className="flex items-center justify-between w-full">
          {/* Left: logo */}
          <Link to="/app" className="flex items-center gap-2.5 group" aria-label="MSTool-AI Home">
            <div className="bg-gradient-to-br from-blue-500 to-purple-600 p-1.5 rounded-lg">
              <Brain className="w-4 h-4 text-white" />
            </div>
            <span className="text-sm font-bold text-gray-800 dark:text-white">MSTool-AI</span>
          </Link>

          {/* Right: controls — consistent spacing, vertically centered */}
          <div className="flex items-center gap-1">
            {rightControls && (
              <>
                {rightControls}
                <div className="w-px h-5 bg-gray-200 dark:bg-gray-700 mx-1" />
              </>
            )}
            <ThemeToggle variant="minimal" />
            <LanguageSelector variant="minimal" />
            <UserMenu />
          </div>
        </div>
      </div>

      {/* LINE 2: Breadcrumb (shows where you are in the hierarchy) */}
      {autoBreadcrumbs.length > 0 && (
        <div className="bg-gray-50/80 dark:bg-gray-800/50 border-b border-gray-200/30 dark:border-gray-700/30 px-5 py-1.5">
          <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-xs">
            {onBack && (
              <button onClick={onBack} className="mr-1 text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors" aria-label="Go back">
                <ChevronRight className="w-3.5 h-3.5 rotate-180" />
              </button>
            )}
            {autoBreadcrumbs.map((item, i) => (
              <span key={i} className="flex items-center gap-1.5">
                {i > 0 && <ChevronRight className="w-3 h-3 text-gray-300 dark:text-gray-600 shrink-0" />}
                {item.path ? (
                  <Link to={item.path} className="text-gray-500 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors">
                    {item.label}
                  </Link>
                ) : (
                  <span className="text-gray-800 dark:text-gray-200 font-medium" aria-current="page">
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
