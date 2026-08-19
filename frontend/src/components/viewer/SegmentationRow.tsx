import type { LucideIcon } from 'lucide-react';
import { ChevronDown, ChevronRight, Eye, EyeOff, Loader2, Trash2 } from 'lucide-react';
import type { SegOrigin } from '../../utils/segmentationList';

type Accent = 'emerald' | 'purple';

/**
 * Provenance badge presentation. A Class C traceability control: a clinician must
 * distinguish a human expert mask from a validated auto-segmenter from the legacy
 * over-segmenter (precision 0.22) without reading names. `ai-legacy` is styled as a
 * warning and labelled research-only; `zonemap`/`manual` render no badge (the zone
 * map has its own emerald identity; manual is the unremarkable default).
 */
const PROVENANCE: Partial<Record<SegOrigin, { label: string; title: string; cls: string }>> = {
  expert: {
    label: 'Experto', title: 'Human expert ground truth',
    cls: 'text-emerald-300 bg-emerald-900/50 border border-emerald-700/50',
  },
  ai: {
    label: 'IA', title: 'Automatic segmentation (validated tool)',
    cls: 'text-cyan-300 bg-cyan-900/40 border border-cyan-700/50',
  },
  'ai-legacy': {
    label: 'IA · investigación', title: 'Legacy AI segmenter — research only (over-segments; precision 0.22)',
    cls: 'text-amber-300 bg-amber-900/40 border border-amber-700/60',
  },
  unknown: {
    label: 'Sin verificar', title: 'Unverified provenance — origin recorded but not a recognised validated tool',
    cls: 'text-gray-300 bg-gray-700/50 border border-gray-600',
  },
};

const ACCENTS: Record<Accent, {
  activeBg: string; chevron: string; iconBase: string; iconActive: string; overlayOn: string;
}> = {
  emerald: {
    activeBg: 'bg-emerald-900/40 border border-emerald-700',
    chevron: 'text-emerald-400',
    iconBase: 'text-emerald-500',
    iconActive: 'text-emerald-500',
    overlayOn: 'text-emerald-400 hover:text-emerald-300',
  },
  purple: {
    activeBg: 'bg-purple-900/50 border border-purple-700',
    chevron: 'text-purple-400',
    iconBase: 'text-purple-500',
    iconActive: 'text-purple-400',
    overlayOn: 'text-purple-400 hover:text-purple-300',
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
 * The header row (chrome) of a sidebar segmentation card. Extracted from two
 * near-identical inline blocks in ViewerApp (Fase 2.2) — MAGNIMS zone map
 * (emerald) and regular segmentation (purple) — that shared this exact markup
 * and differed only by accent colour, icon, and handlers. Parent keeps the
 * card-specific click logic and the expanded content.
 */
export function SegmentationRow({
  name, icon: Icon, accent, highlighted, expanded, overlayOn, isDeleting, origin,
  onRowClick, onToggleOverlay, onDelete,
}: SegmentationRowProps) {
  const a = ACCENTS[accent];
  const prov = origin ? PROVENANCE[origin] : undefined;
  return (
    <div
      onClick={onRowClick}
      className={`cursor-pointer transition-colors ${
        highlighted ? a.activeBg : 'bg-gray-800/60 hover:bg-gray-800 border border-transparent'
      }`}
      style={{ borderRadius: 6, padding: '4px 8px' }}
    >
      <div className="flex items-center" style={{ gap: 6 }}>
        {expanded
          ? <ChevronDown className={`w-3 h-3 flex-shrink-0 ${a.chevron}`} />
          : <ChevronRight className="w-3 h-3 flex-shrink-0 text-gray-400" />}
        <Icon className={`w-3.5 h-3.5 flex-shrink-0 ${highlighted ? a.iconActive : a.iconBase}`} />
        <span className="text-[11px] font-medium truncate flex-1 text-white">{name}</span>
        {prov && (
          <span
            className={`flex-shrink-0 text-[9px] leading-none font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded ${prov.cls}`}
            title={prov.title}
          >
            {prov.label}
          </span>
        )}
        <button
          onClick={onToggleOverlay}
          className={`p-1 rounded transition-colors flex-shrink-0 ${
            overlayOn ? a.overlayOn : 'text-gray-500 hover:text-gray-300'
          }`}
          title={overlayOn ? 'Hide overlay' : 'Show overlay'}
        >
          {overlayOn ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
        </button>
        <button
          onClick={onDelete}
          disabled={isDeleting}
          className="p-1 text-gray-500 hover:text-red-400 transition-colors flex-shrink-0"
        >
          {isDeleting ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
        </button>
      </div>
    </div>
  );
}
