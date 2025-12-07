"""
NIfTI file utilities shared across services.

This module provides common NIfTI file operations to eliminate
code duplication and provide standardized NIfTI handling.
"""

import numpy as np
import nibabel as nib
import tempfile
import os
from typing import Tuple, Optional
from pathlib import Path


def detect_gzip(file_data: bytes) -> bool:
    """
    Detect if file data is gzipped by checking magic bytes.

    Args:
        file_data: Raw file bytes

    Returns:
        True if file is gzipped, False otherwise

    Examples:
        >>> gzip_data = b'\\x1f\\x8b...'
        >>> detect_gzip(gzip_data)
        True
    """
    return file_data[:2] == b'\x1f\x8b'


def load_nifti_from_bytes(
    file_data: bytes,
    normalize: bool = False
) -> Tuple[nib.Nifti1Image, np.ndarray]:
    """
    Load NIfTI image from bytes using temporary file.

    NiBabel requires a file path, so this function writes data to
    a temporary file, loads it, then cleans up.

    Args:
        file_data: Raw NIfTI file bytes
        normalize: If True, normalize data to uint8 (0-255)

    Returns:
        Tuple of (nib.Nifti1Image, numpy array)

    Raises:
        ValueError: If file cannot be loaded as NIfTI

    Examples:
        >>> with open('brain.nii.gz', 'rb') as f:
        ...     data = f.read()
        >>> img, array = load_nifti_from_bytes(data)
        >>> array.shape
        (256, 256, 160)
    """
    # Detect compression
    is_gzipped = detect_gzip(file_data)
    suffix = '.nii.gz' if is_gzipped else '.nii'

    # Write to temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
        tmp_file.write(file_data)
        tmp_path = tmp_file.name

    try:
        # Load NIfTI image
        img = nib.load(tmp_path)
        data = img.get_fdata()

        # Optionally normalize
        if normalize:
            from app.utils.image_utils import normalize_to_uint8
            data = normalize_to_uint8(data)

        return img, data

    finally:
        # Clean up temporary file
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def create_nifti_image(
    data: np.ndarray,
    affine: Optional[np.ndarray] = None,
    header: Optional[nib.Nifti1Header] = None
) -> nib.Nifti1Image:
    """
    Create a NIfTI image from numpy array.

    Args:
        data: Image data as numpy array
        affine: 4x4 affine transformation matrix (default: identity matrix)
        header: Optional NIfTI header (creates default if None)

    Returns:
        NIfTI image object

    Examples:
        >>> data = np.random.rand(100, 100, 50)
        >>> img = create_nifti_image(data)
        >>> img.shape
        (100, 100, 50)
    """
    if affine is None:
        affine = np.eye(4)

    return nib.Nifti1Image(data, affine=affine, header=header)


def save_nifti(
    img: nib.Nifti1Image,
    output_path: str,
    compress: bool = True
) -> str:
    """
    Save NIfTI image to file.

    Args:
        img: NIfTI image to save
        output_path: Output file path
        compress: If True, saves as .nii.gz (compressed)

    Returns:
        Final output path (may be modified for compression)

    Examples:
        >>> img = nib.Nifti1Image(data, np.eye(4))
        >>> path = save_nifti(img, 'output.nii', compress=True)
        >>> path
        'output.nii.gz'
    """
    output_path = Path(output_path)

    # Adjust extension for compression
    if compress and not str(output_path).endswith('.gz'):
        if str(output_path).endswith('.nii'):
            output_path = Path(str(output_path) + '.gz')
        else:
            output_path = Path(str(output_path) + '.nii.gz')
    elif not compress and str(output_path).endswith('.nii.gz'):
        output_path = Path(str(output_path).replace('.nii.gz', '.nii'))

    # Save
    nib.save(img, str(output_path))

    return str(output_path)


def transpose_for_nifti(array: np.ndarray, from_convention: str = 'DHW') -> np.ndarray:
    """
    Transpose array from internal convention to NIfTI convention.

    NIfTI typically uses (Width, Height, Depth) or (X, Y, Z) ordering,
    while our internal representation uses (Depth, Height, Width).

    Args:
        array: Input array
        from_convention: Source convention ('DHW', 'HWD', etc.)

    Returns:
        Transposed array in NIfTI convention (WHD)

    Examples:
        >>> arr_dhw = np.zeros((50, 100, 100))  # (D, H, W)
        >>> arr_whd = transpose_for_nifti(arr_dhw, 'DHW')
        >>> arr_whd.shape
        (100, 100, 50)  # (W, H, D)
    """
    if from_convention == 'DHW':
        # (Depth, Height, Width) -> (Width, Height, Depth)
        return np.transpose(array, (2, 1, 0))
    elif from_convention == 'HWD':
        # (Height, Width, Depth) -> (Width, Height, Depth)
        return np.transpose(array, (1, 0, 2))
    elif from_convention == 'WHD':
        # Already in NIfTI convention
        return array
    else:
        raise ValueError(f"Unsupported convention: {from_convention}")


def transpose_from_nifti(array: np.ndarray, to_convention: str = 'DHW') -> np.ndarray:
    """
    Transpose array from NIfTI convention to internal convention.

    Inverse of transpose_for_nifti.

    Args:
        array: Input array in NIfTI convention (WHD)
        to_convention: Target convention ('DHW', 'HWD', etc.)

    Returns:
        Transposed array in target convention

    Examples:
        >>> arr_whd = np.zeros((100, 100, 50))  # (W, H, D)
        >>> arr_dhw = transpose_from_nifti(arr_whd, 'DHW')
        >>> arr_dhw.shape
        (50, 100, 100)  # (D, H, W)
    """
    if to_convention == 'DHW':
        # (Width, Height, Depth) -> (Depth, Height, Width)
        return np.transpose(array, (2, 1, 0))
    elif to_convention == 'HWD':
        # (Width, Height, Depth) -> (Height, Width, Depth)
        return np.transpose(array, (1, 0, 2))
    elif to_convention == 'WHD':
        # Already in target convention
        return array
    else:
        raise ValueError(f"Unsupported convention: {to_convention}")


def extract_nifti_metadata(img: nib.Nifti1Image) -> dict:
    """
    Extract metadata from NIfTI image.

    Args:
        img: NIfTI image object

    Returns:
        Dictionary with metadata (shape, spacing, orientation, etc.)

    Examples:
        >>> img = nib.load('brain.nii.gz')
        >>> metadata = extract_nifti_metadata(img)
        >>> metadata['shape']
        (256, 256, 160)
    """
    header = img.header
    data_shape = img.shape
    pixdim = header.get_zooms()

    metadata = {
        'shape': data_shape,
        'ndim': len(data_shape),
        'dtype': str(img.get_data_dtype()),
        'pixel_spacing': [float(pixdim[i]) for i in range(min(3, len(pixdim)))],
        'affine': img.affine.tolist(),
        'voxel_sizes': list(pixdim[:3]) if len(pixdim) >= 3 else list(pixdim),
    }

    # Add optional metadata
    if hasattr(header, 'get_xyzt_units'):
        spatial_unit, temporal_unit = header.get_xyzt_units()
        metadata['spatial_unit'] = spatial_unit
        metadata['temporal_unit'] = temporal_unit

    return metadata


def create_segmentation_filename(
    original_filename: str,
    segmentation_id: Optional[str] = None,
    suffix: str = '_segmentation'
) -> str:
    """
    Create a filename for segmentation output from original filename.

    Args:
        original_filename: Original image filename
        segmentation_id: Optional segmentation ID to use if filename generation fails
        suffix: Suffix to add before extension

    Returns:
        New filename for segmentation

    Examples:
        >>> create_segmentation_filename('brain.nii.gz')
        'brain_segmentation.nii.gz'
        >>> create_segmentation_filename('scan.nii', suffix='_labels')
        'scan_labels.nii.gz'
    """
    # Handle .nii.gz extension
    if original_filename.endswith('.nii.gz'):
        return original_filename.replace('.nii.gz', f'{suffix}.nii.gz')

    # Handle .nii extension
    elif original_filename.endswith('.nii'):
        return original_filename.replace('.nii', f'{suffix}.nii.gz')

    # Fallback: just append
    else:
        if segmentation_id:
            return f"{segmentation_id}{suffix}.nii.gz"
        else:
            return f"{original_filename}{suffix}.nii.gz"


def validate_nifti_data(data: np.ndarray, expected_ndim: Optional[int] = None) -> bool:
    """
    Validate NIfTI data array.

    Args:
        data: Numpy array to validate
        expected_ndim: Expected number of dimensions (None = no check)

    Returns:
        True if valid

    Raises:
        ValueError: If validation fails

    Examples:
        >>> data = np.random.rand(100, 100, 50)
        >>> validate_nifti_data(data, expected_ndim=3)
        True
    """
    if not isinstance(data, np.ndarray):
        raise ValueError(f"Data must be numpy array, got {type(data)}")

    if expected_ndim is not None and data.ndim != expected_ndim:
        raise ValueError(
            f"Expected {expected_ndim}D data, got {data.ndim}D with shape {data.shape}"
        )

    if data.size == 0:
        raise ValueError("Data array is empty")

    return True
