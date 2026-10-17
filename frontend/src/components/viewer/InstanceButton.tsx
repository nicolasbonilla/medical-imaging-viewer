import { FileImage, FlaskConical } from 'lucide-react';
import { twMerge } from 'tailwind-merge';
import { detectSequence, SEQUENCE_INFO } from '@/utils/sequenceDetection';

export interface InstanceButtonData {
  id: string;
  original_filename?: string;
  file_size_bytes: number;
}

interface InstanceButtonProps {
  instance: InstanceButtonData;
  selected: boolean;
  onSelect: (id: string) => void;
  variant: 'original' | 'preprocessed';
}

/**
 * A single study-instance row in the viewer sidebar (v2 tokens). `variant` keeps the
 * original / preprocessed distinction (icon + fallback label); the detected MRI
 * sequence is shown as a short chip so FLAIR vs T1 is readable at a glance.
 */
export function InstanceButton({ instance, selected, onSelect, variant }: InstanceButtonProps) {
  const isOriginal = variant === 'original';
  const Icon = isOriginal ? FileImage : FlaskConical;
  const fallbackName = isOriginal ? 'Image' : 'Preprocessed';
  const seq = detectSequence(instance.original_filename || '');

  return (
    <button
      type="button"
      onClick={() => onSelect(instance.id)}
      aria-pressed={selected}
      className={twMerge(
        'group w-full rounded-lg border px-2 py-1.5 text-left transition-colors',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60',
        selected
          ? 'border-brand-500/40 bg-brand-950/70 text-ink-base'
          : 'border-transparent bg-surface-raised/50 text-ink-soft hover:bg-surface-raised hover:text-ink-base',
      )}
    >
      <div className="flex items-center gap-2">
        <Icon className={twMerge('h-4 w-4 shrink-0', selected ? 'text-brand-400' : 'text-ink-faint')} aria-hidden />
        {seq !== 'unknown' && (
          <span className="shrink-0 rounded bg-surface-hover px-1.5 py-0.5 text-xs font-semibold leading-none text-ink-soft">
            {SEQUENCE_INFO[seq].shortLabel}
          </span>
        )}
        <p className="min-w-0 flex-1 truncate text-xs font-medium" title={instance.original_filename || fallbackName}>
          {instance.original_filename || fallbackName}
        </p>
        <span className="shrink-0 text-xs tabular-nums text-ink-faint">
          {(instance.file_size_bytes / 1024 / 1024).toFixed(1)}MB
        </span>
      </div>
    </button>
  );
}
