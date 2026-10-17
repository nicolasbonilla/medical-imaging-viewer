/** Colour maps offered for the 3D (niivue) volume — kept out of ImageViewer3D so
 *  side panels do not pull the WebGL engine into their chunk. */
export const COLORMAPS_3D = [
  { id: 'gray', label: 'Gray' },
  { id: 'hot', label: 'Hot' },
  { id: 'bone', label: 'Bone' },
  { id: 'winter', label: 'Winter' },
  { id: 'viridis', label: 'Viridis' },
  { id: 'cool', label: 'Cool' },
  { id: 'ge_color', label: 'GE Color' },
  { id: 'inferno', label: 'Inferno' },
] as const;
