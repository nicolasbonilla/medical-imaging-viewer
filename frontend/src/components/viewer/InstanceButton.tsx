import { FileImage, FlaskConical } from 'lucide-react';

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
 * A single study-instance row in the viewer sidebar. Extracted from two
 * byte-identical inline blocks in ViewerApp (Fase 2.2) that differed only by
 * icon/accent colour and the fallback label — now a single component keyed by
 * `variant`.
 */
export function InstanceButton({ instance, selected, onSelect, variant }: InstanceButtonProps) {
  const isOriginal = variant === 'original';
  const Icon = isOriginal ? FileImage : FlaskConical;
  const selectedBg = isOriginal ? 'bg-blue-600' : 'bg-teal-600';
  const iconColor = isOriginal ? 'text-blue-500' : 'text-teal-500';
  const fallbackName = isOriginal ? 'Image' : 'Preprocessed';

  return (
    <button
      onClick={() => onSelect(instance.id)}
      className={`w-full text-left transition-colors ${
        selected ? `${selectedBg} text-white` : 'bg-gray-800/60 hover:bg-gray-800 text-gray-300'
      }`}
      style={{ padding: '4px 8px', borderRadius: 6 }}
    >
      <div className="flex items-center gap-2">
        <Icon className={`w-3.5 h-3.5 flex-shrink-0 ${selected ? 'text-white' : iconColor}`} />
        <p className="text-[11px] font-medium truncate flex-1">
          {instance.original_filename || fallbackName}
        </p>
        <span className={`text-[10px] ${selected ? 'text-white/70' : 'text-gray-400'}`}>
          {(instance.file_size_bytes / 1024 / 1024).toFixed(1)}MB
        </span>
      </div>
    </button>
  );
}
