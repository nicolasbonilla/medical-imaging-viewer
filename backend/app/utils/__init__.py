"""
Shared utility modules for backend services.

This package contains utility functions shared across multiple services
to eliminate code duplication and improve maintainability.
"""

from app.utils.image_utils import (
    normalize_to_uint8,
    array_to_base64,
    hex_to_rgb,
    rgb_to_hex,
    decode_base64_image,
    ensure_3d_array,
    apply_alpha_blending,
    create_rgba_overlay,
    combine_mask_overlays
)

from app.utils.nifti_utils import (
    detect_gzip,
    load_nifti_from_bytes,
    create_nifti_image,
    save_nifti,
    transpose_for_nifti,
    transpose_from_nifti,
    extract_nifti_metadata,
    create_segmentation_filename,
    validate_nifti_data
)

from app.utils.dicom_utils import (
    create_file_meta,
    create_dicom_dataset,
    set_patient_info,
    set_study_info,
    set_series_info,
    set_image_info,
    set_spatial_info,
    set_datetime_info,
    numpy_to_dicom_pixel_data,
    save_dicom,
    create_segmentation_dicom,
    extract_dicom_metadata
)

__all__ = [
    # image_utils
    'normalize_to_uint8',
    'array_to_base64',
    'hex_to_rgb',
    'rgb_to_hex',
    'decode_base64_image',
    'ensure_3d_array',
    'apply_alpha_blending',
    'create_rgba_overlay',
    'combine_mask_overlays',
    # nifti_utils
    'detect_gzip',
    'load_nifti_from_bytes',
    'create_nifti_image',
    'save_nifti',
    'transpose_for_nifti',
    'transpose_from_nifti',
    'extract_nifti_metadata',
    'create_segmentation_filename',
    'validate_nifti_data',
    # dicom_utils
    'create_file_meta',
    'create_dicom_dataset',
    'set_patient_info',
    'set_study_info',
    'set_series_info',
    'set_image_info',
    'set_spatial_info',
    'set_datetime_info',
    'numpy_to_dicom_pixel_data',
    'save_dicom',
    'create_segmentation_dicom',
    'extract_dicom_metadata',
]
