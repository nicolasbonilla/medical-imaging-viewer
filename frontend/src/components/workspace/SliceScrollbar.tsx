/**
 * Vertical stack scrollbar along the right edge of the image (v3) — the long-range
 * slice navigator, as in clinical viewers. Up = higher slice number (same direction as
 * the toolbar's "next slice"). Keyboard: arrows / PageUp / PageDown / Home / End.
 */
import { useTranslation } from 'react-i18next';
import { useActiveSliceInfo } from '@/hooks/useActiveSliceInfo';

export function SliceScrollbar() {
  const { t } = useTranslation();
  const slice = useActiveSliceInfo();
  if (slice.totalSlices <= 1) return null;
  return (
    <div className="pointer-events-none absolute bottom-12 right-2 top-12 z-20 flex w-5 justify-center">
      <input
        type="range"
        min={0}
        max={slice.totalSlices - 1}
        value={slice.sliceIndex}
        onChange={(e) => slice.setSliceIndex(parseInt(e.target.value, 10))}
        aria-label={t('viewer3.sliceSlider', 'Slice position')}
        aria-valuetext={`${slice.sliceIndex + 1} / ${slice.totalSlices}`}
        className="pointer-events-auto h-full w-1 cursor-pointer appearance-none rounded-full bg-white/10 accent-brand-500 opacity-60 transition-opacity hover:opacity-100 focus:opacity-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60"
        style={{ writingMode: 'vertical-lr', direction: 'rtl' }}
      />
    </div>
  );
}

export default SliceScrollbar;
