/**
 * Slider component for slice navigation.
 * Allows users to scrub through slices with a range input.
 */

interface SliceSliderProps {
  currentSliceIndex: number;
  totalSlices: number;
  onChange: (index: number) => void;
}

export function SliceSlider({ currentSliceIndex, totalSlices, onChange }: SliceSliderProps) {
  return (
    <div className="absolute bottom-4 left-1/2 transform -translate-x-1/2 bg-gray-900 bg-opacity-90 rounded-lg px-6 py-3">
      <input
        type="range"
        min="0"
        max={totalSlices - 1}
        value={currentSliceIndex}
        onChange={(e) => onChange(parseInt(e.target.value))}
        className="w-64"
      />
    </div>
  );
}
