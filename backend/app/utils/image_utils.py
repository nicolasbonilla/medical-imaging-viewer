"""
Image utility functions shared across services.

This module provides common image processing operations to eliminate
code duplication between imaging_service and segmentation_service.
"""

import numpy as np
import base64
import io
from typing import Tuple, Optional, Union
from PIL import Image


def normalize_to_uint8(array: np.ndarray) -> np.ndarray:
    """
    Normalize array to 0-255 uint8 range.

    This function handles arrays of any data type and normalizes them
    to the standard 0-255 uint8 range used for image display.

    Args:
        array: Input numpy array of any dtype

    Returns:
        Normalized array as uint8

    Examples:
        >>> arr = np.array([[0.0, 0.5], [1.0, 1.5]])
        >>> result = normalize_to_uint8(arr)
        >>> result.dtype
        dtype('uint8')
    """
    # Already uint8, return as-is
    if array.dtype == np.uint8:
        return array

    # Convert to float for calculation
    array = array.astype(np.float64)
    arr_min = array.min()
    arr_max = array.max()

    # Normalize to 0-255 range
    if arr_max > arr_min:
        normalized = ((array - arr_min) / (arr_max - arr_min) * 255.0)
    else:
        # All values are the same, return zeros
        normalized = np.zeros_like(array)

    return normalized.astype(np.uint8)


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """
    Convert hex color string to RGB tuple.

    Args:
        hex_color: Hex color string (e.g., '#FF0000' or 'FF0000')

    Returns:
        RGB tuple (r, g, b) with values 0-255

    Examples:
        >>> hex_to_rgb('#FF0000')
        (255, 0, 0)
        >>> hex_to_rgb('00FF00')
        (0, 255, 0)
    """
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    """
    Convert RGB tuple to hex color string.

    Args:
        rgb: RGB tuple (r, g, b) with values 0-255

    Returns:
        Hex color string with '#' prefix

    Examples:
        >>> rgb_to_hex((255, 0, 0))
        '#FF0000'
        >>> rgb_to_hex((0, 255, 0))
        '#00FF00'
    """
    return '#{:02X}{:02X}{:02X}'.format(*rgb)


def array_to_base64(
    array: np.ndarray,
    mode: str = 'auto',
    include_data_url_prefix: bool = True
) -> str:
    """
    Convert numpy array to base64 encoded PNG.

    Unified implementation supporting grayscale, RGB, and RGBA images.

    Args:
        array: Input numpy array (2D for grayscale, 3D for RGB/RGBA)
        mode: PIL image mode ('L', 'RGB', 'RGBA', or 'auto' for auto-detection)
        include_data_url_prefix: If True, includes 'data:image/png;base64,' prefix

    Returns:
        Base64 encoded PNG string

    Raises:
        ValueError: If array shape is not supported

    Examples:
        >>> arr = np.zeros((100, 100), dtype=np.uint8)
        >>> b64 = array_to_base64(arr, mode='L')
        >>> b64.startswith('data:image/png;base64,')
        True
    """
    # Normalize to uint8 if needed
    if array.dtype != np.uint8:
        array = normalize_to_uint8(array)

    # Auto-detect mode if requested
    if mode == 'auto':
        if len(array.shape) == 2:
            mode = 'L'  # Grayscale
        elif len(array.shape) == 3:
            if array.shape[2] == 3:
                mode = 'RGB'
            elif array.shape[2] == 4:
                mode = 'RGBA'
            else:
                raise ValueError(
                    f"Unsupported array shape for image conversion: {array.shape}. "
                    f"Expected 2D (grayscale) or 3D with 3 (RGB) or 4 (RGBA) channels."
                )
        else:
            raise ValueError(
                f"Unsupported array shape: {array.shape}. "
                f"Expected 2D or 3D array."
            )

    # Create PIL Image
    image = Image.fromarray(array, mode=mode)

    # Save to buffer as PNG
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    buffer.seek(0)

    # Encode to base64
    img_b64 = base64.b64encode(buffer.read()).decode('utf-8')

    # Add data URL prefix if requested
    if include_data_url_prefix:
        return f"data:image/png;base64,{img_b64}"
    else:
        return img_b64


def decode_base64_image(data_url: str) -> np.ndarray:
    """
    Decode base64 encoded image to numpy array.

    Args:
        data_url: Base64 encoded image string (with or without data URL prefix)

    Returns:
        Numpy array representation of the image

    Examples:
        >>> data_url = 'data:image/png;base64,iVBORw0KG...'
        >>> arr = decode_base64_image(data_url)
        >>> isinstance(arr, np.ndarray)
        True
    """
    # Remove data URL prefix if present
    if data_url.startswith('data:image'):
        data_url = data_url.split(',', 1)[1]

    # Decode base64
    image_data = base64.b64decode(data_url)

    # Load as PIL Image
    image = Image.open(io.BytesIO(image_data))

    # Convert to numpy array
    return np.array(image)


def ensure_3d_array(array: np.ndarray, target_axis: int = 2) -> np.ndarray:
    """
    Ensure array is 3D by adding a dimension if necessary.

    This is useful when processing medical images that may be 2D or 3D.

    Args:
        array: Input numpy array (2D or 3D)
        target_axis: Axis along which to add dimension for 2D arrays (default: 2)

    Returns:
        3D numpy array

    Examples:
        >>> arr_2d = np.zeros((100, 100))
        >>> arr_3d = ensure_3d_array(arr_2d)
        >>> arr_3d.shape
        (100, 100, 1)
    """
    if len(array.shape) == 2:
        return np.expand_dims(array, axis=target_axis)
    return array


def apply_alpha_blending(
    base: np.ndarray,
    overlay: np.ndarray,
    alpha: float
) -> np.ndarray:
    """
    Apply alpha blending to combine base and overlay images.

    Both arrays must have the same shape or be broadcastable.

    Args:
        base: Base image array
        overlay: Overlay image array
        alpha: Opacity factor (0.0 = fully transparent, 1.0 = fully opaque)

    Returns:
        Blended image array

    Examples:
        >>> base = np.ones((100, 100, 3), dtype=np.uint8) * 255
        >>> overlay = np.zeros((100, 100, 3), dtype=np.uint8)
        >>> result = apply_alpha_blending(base, overlay, 0.5)
        >>> result[0, 0, 0]
        127
    """
    # Ensure both are float for blending
    base_float = base.astype(np.float32)
    overlay_float = overlay.astype(np.float32)

    # Apply alpha blending formula: result = overlay * alpha + base * (1 - alpha)
    blended = overlay_float * alpha + base_float * (1.0 - alpha)

    # Convert back to original dtype
    return blended.astype(base.dtype)


def create_rgba_overlay(
    mask: np.ndarray,
    color: Tuple[int, int, int],
    opacity: float = 0.5
) -> np.ndarray:
    """
    Create an RGBA overlay from a binary mask and color.

    Args:
        mask: Binary mask array (0 or 1 values)
        color: RGB color tuple (r, g, b) with values 0-255
        opacity: Opacity for non-zero mask pixels (0.0 to 1.0)

    Returns:
        RGBA array with shape (H, W, 4)

    Examples:
        >>> mask = np.array([[0, 1], [1, 0]])
        >>> overlay = create_rgba_overlay(mask, (255, 0, 0), opacity=0.5)
        >>> overlay.shape
        (2, 2, 4)
    """
    # Ensure mask is 2D
    if len(mask.shape) != 2:
        raise ValueError(f"Mask must be 2D, got shape {mask.shape}")

    h, w = mask.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)

    # Apply color where mask is non-zero
    rgba[..., 0] = color[0] * mask  # R
    rgba[..., 1] = color[1] * mask  # G
    rgba[..., 2] = color[2] * mask  # B
    rgba[..., 3] = (255 * opacity * mask).astype(np.uint8)  # A

    return rgba


def combine_mask_overlays(
    masks: list[np.ndarray],
    colors: list[Tuple[int, int, int]],
    opacities: list[float]
) -> np.ndarray:
    """
    Combine multiple binary masks with different colors into single RGBA overlay.

    Args:
        masks: List of binary mask arrays (same shape)
        colors: List of RGB color tuples
        opacities: List of opacity values

    Returns:
        Combined RGBA array

    Raises:
        ValueError: If lists have different lengths or masks have different shapes
    """
    if not (len(masks) == len(colors) == len(opacities)):
        raise ValueError("masks, colors, and opacities must have the same length")

    if not masks:
        raise ValueError("At least one mask is required")

    # Get output shape from first mask
    h, w = masks[0].shape
    combined = np.zeros((h, w, 4), dtype=np.float32)

    # Combine masks in order (later masks take precedence)
    for mask, color, opacity in zip(masks, colors, opacities):
        if mask.shape != (h, w):
            raise ValueError(f"All masks must have the same shape. Expected {(h, w)}, got {mask.shape}")

        # Create overlay for this mask
        overlay = create_rgba_overlay(mask, color, opacity).astype(np.float32)

        # Blend with combined (simple overwrite where mask is non-zero)
        mask_bool = mask > 0
        combined[mask_bool] = overlay[mask_bool]

    return combined.astype(np.uint8)
