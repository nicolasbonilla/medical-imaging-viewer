import type { LucideIcon } from 'lucide-react';
import { ChevronRight, Eye, EyeOff, Loader2, Trash2 } from 'lucide-react';
import { twMerge } from 'tailwind-merge';
import type { SegOrigin } from '../../utils/segmentationList';
import { Badge } from '../ui';

type Accent = 'emerald' | 'purple';

/**
 * Provenance badge presentation. A Class C traceability control: a clinician must
 * distinguish a human expert mask from a validated auto-segmenter from the legacy
 * over-segmenter (precision 0.22) without reading names. `ai-legacy` is styled as a
 * warning and labelled research-only; `zonemap`/`manual` render no badge (the zone
 * map has its own identity; manual is the unremarkable default).
 */
const PROVENANCE: Partial<Record<SegOrigin, { label: string; title: string; tone: 'good' | 'info' | 'warn' | 'neutral' }>> = {
  expert: { label: 'Experto', title: 'Human expert ground truth', tone: 'good' },
  ai: { label: 'IA', title: 'Automatic segmentation (validated tool)', tone: 'info' },
  'ai-legacy': {
    label: 'IA · investigación',
    title: 'Legacy AI segmenter — research only (over-segments; precision 0.22)',
    tone: 'warn',
  },
  unknown: {
    label: 'Sin verificar',
    title: 'Unverified provenance — origin recorded but not a recognised validated tool',
    tone: 'neutral',
  },
};

/** emerald = MAGNIMS zone map layer, purple = lesion segmentation (v2 tokens). */
const ACCENTS: Record<Accent, { active: string; icon: string; overlayOn: string }> = {
  emerald: {
    active: 'border-clinical-good/40 bg-clinical-good/10',
    icon: 'text-clinical-good',
    overlayOn: 'text-clinical-good',
  },
  purple: {
    active: 'border-brand-500/40 bg-brand-950/70',
    icon: 'text-brand-400',
    overlayOn: 'text-brand-400',
  },
};

interface SegmentationRowProps {
  name: string;
  icon: LucideIcon;
  accent: Accent;
  /** Drives the active/highlighted background (isExpanded for zone maps, isActive for segmentations). */
  highlighted: boolean;
  /** Chevron direction. */
  expanded: boolean;
  /** Overlay visible → filled Eye + accent colour. */
  overlayOn: boolean;
  isDeleting: boolean;
  /** Mask provenance — drives the traceability badge (Class C). Omit for zone maps. */
  origin?: SegOrigin;
  onRowClick: () => void;
  onToggleOverlay: (e: React.MouseEvent) => void;
  onDelete: (e: React.MouseEvent) => void;
}

/**
 * The header row (chrome) of a sidebar segmentation card. The whole row is the
 * primary action (open / expand) and is keyboard reachable; the overlay and delete
 * controls are separate buttons that do not bubble to the row.
 */
export function SegmentationRow({
  name, icon: Icon, accent, highlighted, expanded, overlayOn, isDeleting, origin,
  onRowClick, onToggleOverlay, onDelete,
}: SegmentationRowProps) {
  const a = ACCENTS[accent];
  const prov = origin ? PROVENANCE[origin] : undefined;
  return (
    // Mouse: the whole row opens it. Keyboard: the name button is the primary action;
    // its click (Enter / Space) bubbles here. Overlay / delete stop propagation.
    <div
      onClick={onRowClick}
      data-seg-row
      className={twMerge(
        'group flex cursor-pointer items-center gap-2 rounded-lg border px-2 py-2 transition-colors',
        highlighted ? a.active : 'border-transparent bg-surface-raised/50 hover:bg-surface-raised',
      )}
    >
      <button
        type="button"
        aria-expanded={expanded}
        className="flex min-w-0 flex-1 items-start gap-2 rounded text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60"
      >
        <ChevronRight
          className={twMerge('mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-faint transition-transform', expanded && 'rotate-90 text-ink-soft')}
          aria-hidden
        />
        <Icon className={twMerge('mt-px h-4 w-4 shrink-0', highlighted ? a.icon : 'text-ink-muted')} aria-hidden />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-xs font-medium text-ink-base" title={name}>{name}</span>
          {prov && (
            // Provenance on its own line so the name is readable in a narrow rail.
            <Badge tone={prov.tone} title={prov.title} className="mt-1 px-1.5 py-0.5">
              {prov.label}
            </Badge>
          )}
        </span>
      </button>
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); onToggleOverlay(e); }}
        className={twMerge(
          'shrink-0 rounded-md p-1 transition-colors hover:bg-surface-hover',
          'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60',
          overlayOn ? a.overlayOn : 'text-ink-faint hover:text-ink-soft',
        )}
        title={overlayOn ? 'Hide overlay' : 'Show overlay'}
        aria-label={overlayOn ? 'Hide overlay' : 'Show overlay'}
        aria-pressed={overlayOn}
      >
        {overlayOn ? <Eye className="h-3.5 w-3.5" aria-hidden /> : <EyeOff className="h-3.5 w-3.5" aria-hidden />}
      </button>
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); onDelete(e); }}
        disabled={isDeleting}
        className="shrink-0 rounded-md p-1 text-ink-faint transition-colors hover:bg-clinical-crit/10 hover:text-clinical-crit focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60 disabled:opacity-40"
        title="Delete segmentation"
        aria-label="Delete segmentation"
      >
        {isDeleting ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> : <Trash2 className="h-3.5 w-3.5" aria-hidden />}
      </button>
    </div>
  );
}
