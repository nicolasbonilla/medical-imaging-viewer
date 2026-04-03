"""
DICOM file utilities shared across services.

This module provides common DICOM operations to eliminate
code duplication and provide standardized DICOM handling.
"""

import numpy as np
import pydicom
from pydicom.dataset import Dataset, FileDataset
from pydicom.uid import generate_uid
from datetime import datetime
from typing import Optional, Tuple, Dict, Any
from pathlib import Path


def create_file_meta(
    sop_class_uid: str = '1.2.840.10008.5.1.4.1.1.7',  # Secondary Capture
    transfer_syntax_uid: str = '1.2.840.10008.1.2.1'  # Explicit VR Little Endian
) -> Dataset:
    """
    Create DICOM file meta information.

    Args:
        sop_class_uid: SOP Class UID (default: Secondary Capture)
        transfer_syntax_uid: Transfer Syntax UID (default: Explicit VR Little Endian)

    Returns:
        Dataset with file meta information

    Examples:
        >>> file_meta = create_file_meta()
        >>> file_meta.MediaStorageSOPClassUID
        '1.2.840.10008.5.1.4.1.1.7'
    """
    file_meta = Dataset()
    file_meta.MediaStorageSOPClassUID = sop_class_uid
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = transfer_syntax_uid
    file_meta.ImplementationClassUID = generate_uid()

    return file_meta


def create_dicom_dataset(
    filename: str,
    file_meta: Optional[Dataset] = None,
    preamble_size: int = 128
) -> FileDataset:
    """
    Create an empty DICOM FileDataset.

    Args:
        filename: Filename for the dataset
        file_meta: Optional file meta information (creates default if None)
        preamble_size: Size of preamble in bytes (default: 128)

    Returns:
        Empty DICOM FileDataset ready to be populated

    Examples:
        >>> ds = create_dicom_dataset('output.dcm')
        >>> isinstance(ds, FileDataset)
        True
    """
    if file_meta is None:
        file_meta = create_file_meta()

    ds = FileDataset(
        filename,
        {},
        file_meta=file_meta,
        preamble=b"\0" * preamble_size
    )

    return ds


def set_patient_info(
    ds: FileDataset,
    patient_id: str,
    patient_name: Optional[str] = None
) -> FileDataset:
    """
    Set patient information in DICOM dataset.

    Args:
        ds: DICOM dataset to modify
        patient_id: Patient ID
        patient_name: Optional patient name (uses patient_id if None)

    Returns:
        Modified dataset

    Examples:
        >>> ds = create_dicom_dataset('test.dcm')
        >>> ds = set_patient_info(ds, 'PATIENT001', 'John Doe')
        >>> ds.PatientID
        'PATIENT001'
    """
    ds.PatientID = patient_id[:64]  # Limit to 64 characters
    ds.PatientName = (patient_name or patient_id)[:64]

    return ds


def set_study_info(
    ds: FileDataset,
    study_uid: Optional[str] = None,
    series_uid: Optional[str] = None,
    study_description: Optional[str] = None
) -> FileDataset:
    """
    Set study and series information in DICOM dataset.

    Args:
        ds: DICOM dataset to modify
        study_uid: Study Instance UID (generates new if None)
        series_uid: Series Instance UID (generates new if None)
        study_description: Optional study description

    Returns:
        Modified dataset

    Examples:
        >>> ds = create_dicom_dataset('test.dcm')
        >>> ds = set_study_info(ds, study_description='Brain MRI')
        >>> ds.StudyDescription
        'Brain MRI'
    """
    ds.StudyInstanceUID = study_uid or generate_uid()
    ds.SeriesInstanceUID = series_uid or generate_uid()
    ds.SOPInstanceUID = ds.file_meta.MediaStorageSOPInstanceUID
    ds.SOPClassUID = ds.file_meta.MediaStorageSOPClassUID

    if study_description:
        ds.StudyDescription = study_description

    return ds


def set_series_info(
    ds: FileDataset,
    modality: str = 'OT',
    series_description: Optional[str] = None,
    series_number: int = 1,
    instance_number: int = 1
) -> FileDataset:
    """
    Set series-level information in DICOM dataset.

    Args:
        ds: DICOM dataset to modify
        modality: Modality code (e.g., 'CT', 'MR', 'SEG', 'OT')
        series_description: Optional series description
        series_number: Series number (default: 1)
        instance_number: Instance number (default: 1)

    Returns:
        Modified dataset

    Examples:
        >>> ds = create_dicom_dataset('test.dcm')
        >>> ds = set_series_info(ds, modality='SEG', series_description='Segmentation')
        >>> ds.Modality
        'SEG'
    """
    ds.Modality = modality
    ds.SeriesNumber = series_number
    ds.InstanceNumber = instance_number

    if series_description:
        ds.SeriesDescription = series_description

    return ds


def set_image_info(
    ds: FileDataset,
    rows: int,
    columns: int,
    pixel_data: np.ndarray,
    photometric_interpretation: str = 'MONOCHROME2',
    bits_allocated: int = 16,
    samples_per_pixel: int = 1
) -> FileDataset:
    """
    Set image-level information and pixel data in DICOM dataset.

    Args:
        ds: DICOM dataset to modify
        rows: Number of rows
        columns: Number of columns
        pixel_data: Numpy array with pixel data
        photometric_interpretation: Color interpretation (default: MONOCHROME2)
        bits_allocated: Bits allocated per pixel (8 or 16)
        samples_per_pixel: Samples per pixel (1 for grayscale, 3 for RGB)

    Returns:
        Modified dataset

    Examples:
        >>> ds = create_dicom_dataset('test.dcm')
        >>> pixel_array = np.zeros((256, 256), dtype=np.uint16)
        >>> ds = set_image_info(ds, 256, 256, pixel_array)
        >>> ds.Rows
        256
    """
    ds.Rows = rows
    ds.Columns = columns
    ds.SamplesPerPixel = samples_per_pixel
    ds.PhotometricInterpretation = photometric_interpretation
    ds.BitsAllocated = bits_allocated
    ds.BitsStored = bits_allocated
    ds.HighBit = bits_allocated - 1
    ds.PixelRepresentation = 0  # Unsigned

    # Convert pixel data to appropriate type and set
    if bits_allocated == 8:
        pixel_array = pixel_data.astype(np.uint8)
    elif bits_allocated == 16:
        pixel_array = pixel_data.astype(np.uint16)
    else:
        raise ValueError(f"Unsupported bits_allocated: {bits_allocated}")

    ds.PixelData = pixel_array.tobytes()

    return ds


def set_spatial_info(
    ds: FileDataset,
    pixel_spacing: Tuple[float, float] = (1.0, 1.0),
    slice_thickness: float = 1.0,
    slice_location: Optional[float] = None,
    image_position: Optional[Tuple[float, float, float]] = None,
    image_orientation: Optional[Tuple[float, ...]] = None
) -> FileDataset:
    """
    Set spatial/geometric information in DICOM dataset.

    Args:
        ds: DICOM dataset to modify
        pixel_spacing: (row spacing, column spacing) in mm
        slice_thickness: Slice thickness in mm
        slice_location: Optional slice location
        image_position: Optional image position (x, y, z)
        image_orientation: Optional image orientation (6 values)

    Returns:
        Modified dataset

    Examples:
        >>> ds = create_dicom_dataset('test.dcm')
        >>> ds = set_spatial_info(ds, pixel_spacing=(0.5, 0.5), slice_thickness=3.0)
        >>> ds.PixelSpacing
        [0.5, 0.5]
    """
    ds.PixelSpacing = list(pixel_spacing)
    ds.SliceThickness = slice_thickness

    if slice_location is not None:
        ds.SliceLocation = float(slice_location)

    if image_position is not None:
        ds.ImagePositionPatient = list(image_position)
    else:
        # Default position
        ds.ImagePositionPatient = [0.0, 0.0, 0.0]

    if image_orientation is not None:
        ds.ImageOrientationPatient = list(image_orientation)
    else:
        # Default orientation (axial)
        ds.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]

    return ds


def set_datetime_info(
    ds: FileDataset,
    dt: Optional[datetime] = None
) -> FileDataset:
    """
    Set date/time information in DICOM dataset.

    Args:
        ds: DICOM dataset to modify
        dt: Datetime to use (uses current time if None)

    Returns:
        Modified dataset

    Examples:
        >>> ds = create_dicom_dataset('test.dcm')
        >>> ds = set_datetime_info(ds)
        >>> hasattr(ds, 'ContentDate')
        True
    """
    if dt is None:
        dt = datetime.now()

    date_str = dt.strftime('%Y%m%d')
    time_str = dt.strftime('%H%M%S')

    ds.ContentDate = date_str
    ds.ContentTime = time_str
    ds.StudyDate = date_str
    ds.StudyTime = time_str
    ds.SeriesDate = date_str
    ds.SeriesTime = time_str

    return ds


def numpy_to_dicom_pixel_data(
    array: np.ndarray,
    bits: int = 16
) -> bytes:
    """
    Convert numpy array to DICOM pixel data bytes.

    Args:
        array: Numpy array with pixel data
        bits: Bits per pixel (8 or 16)

    Returns:
        Pixel data as bytes

    Examples:
        >>> arr = np.zeros((256, 256), dtype=np.uint8)
        >>> pixel_bytes = numpy_to_dicom_pixel_data(arr, bits=8)
        >>> isinstance(pixel_bytes, bytes)
        True
    """
    if bits == 8:
        return array.astype(np.uint8).tobytes()
    elif bits == 16:
        return array.astype(np.uint16).tobytes()
    else:
        raise ValueError(f"Unsupported bits: {bits}. Use 8 or 16.")


def save_dicom(
    ds: FileDataset,
    output_path: str,
    write_like_original: bool = False
) -> str:
    """
    Save DICOM dataset to file.

    Args:
        ds: DICOM dataset to save
        output_path: Output file path
        write_like_original: If True, preserves original encoding

    Returns:
        Output path

    Examples:
        >>> ds = create_dicom_dataset('output.dcm')
        >>> path = save_dicom(ds, 'output.dcm')
        >>> Path(path).exists()
        True
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ds.save_as(str(output_path), write_like_original=write_like_original)

    return str(output_path)


def create_segmentation_dicom(
    pixel_data: np.ndarray,
    rows: int,
    columns: int,
    slice_index: int,
    patient_id: str,
    series_description: str = "Segmentation",
    output_filename: Optional[str] = None
) -> FileDataset:
    """
    Create a complete DICOM dataset for a segmentation slice.

    This is a convenience function that combines all the individual
    setter functions to create a complete segmentation DICOM.

    Args:
        pixel_data: Pixel data as numpy array
        rows: Number of rows
        columns: Number of columns
        slice_index: Slice index/number
        patient_id: Patient ID
        series_description: Series description
        output_filename: Optional output filename

    Returns:
        Complete DICOM FileDataset

    Examples:
        >>> pixel_data = np.zeros((256, 256), dtype=np.uint16)
        >>> ds = create_segmentation_dicom(pixel_data, 256, 256, 0, 'PATIENT001')
        >>> ds.Modality
        'SEG'
    """
    if output_filename is None:
        output_filename = f"seg_{slice_index:04d}.dcm"

    # Create base dataset
    file_meta = create_file_meta()
    ds = create_dicom_dataset(output_filename, file_meta)

    # Set all information
    set_patient_info(ds, patient_id)
    set_study_info(ds)
    set_series_info(ds, modality='SEG', series_description=series_description, instance_number=slice_index + 1)
    set_image_info(ds, rows, columns, pixel_data)
    set_spatial_info(ds, slice_location=float(slice_index), image_position=(0, 0, float(slice_index)))
    set_datetime_info(ds)

    return ds


def extract_dicom_metadata(ds: FileDataset) -> Dict[str, Any]:
    """
    Extract metadata from DICOM dataset.

    Args:
        ds: DICOM dataset

    Returns:
        Dictionary with extracted metadata

    Examples:
        >>> ds = pydicom.dcmread('example.dcm')
        >>> metadata = extract_dicom_metadata(ds)
        >>> 'PatientID' in metadata
        True
    """
    metadata = {}

    # Patient info
    if hasattr(ds, 'PatientID'):
        metadata['patient_id'] = ds.PatientID
    if hasattr(ds, 'PatientName'):
        metadata['patient_name'] = str(ds.PatientName)

    # Study info
    if hasattr(ds, 'StudyInstanceUID'):
        metadata['study_uid'] = ds.StudyInstanceUID
    if hasattr(ds, 'SeriesInstanceUID'):
        metadata['series_uid'] = ds.SeriesInstanceUID

    # Image info
    if hasattr(ds, 'Rows'):
        metadata['rows'] = int(ds.Rows)
    if hasattr(ds, 'Columns'):
        metadata['columns'] = int(ds.Columns)
    if hasattr(ds, 'Modality'):
        metadata['modality'] = ds.Modality

    # Spatial info
    if hasattr(ds, 'PixelSpacing'):
        metadata['pixel_spacing'] = [float(x) for x in ds.PixelSpacing]
    if hasattr(ds, 'SliceThickness'):
        metadata['slice_thickness'] = float(ds.SliceThickness)

    return metadata


# ============================================================================
# DICOM-SEG (Segmentation Storage)
# ============================================================================

# SOP Class UID for Segmentation Storage
SEGMENTATION_STORAGE_UID = '1.2.840.10008.5.1.4.1.1.66.4'


def create_dicom_seg(
    mask_3d: np.ndarray,
    labels: list,
    patient_name: str = '',
    patient_id: str = '',
    study_instance_uid: Optional[str] = None,
    series_instance_uid: Optional[str] = None,
    study_description: str = '',
    series_description: str = 'Segmentation',
    rows: Optional[int] = None,
    columns: Optional[int] = None,
) -> FileDataset:
    """
    Create a DICOM Segmentation (DICOM-SEG) object from a 3D mask.

    Encodes the segmentation as a multi-frame DICOM-SEG with BINARY
    segmentation type. Each label becomes a separate segment with its
    own color and description.

    Args:
        mask_3d: Segmentation mask, shape (D, H, W), dtype uint8.
                 Values 0=background, 1..N=label IDs.
        labels: List of dicts with {id, name, color} for each label.
        patient_name: Patient name for DICOM header.
        patient_id: Patient ID for DICOM header.
        study_instance_uid: Link to original study (for PACS co-location).
        series_instance_uid: Will be auto-generated if not provided.
        study_description: Study description string.
        series_description: Series description string.
        rows: Image rows (auto-detected from mask if None).
        columns: Image columns (auto-detected from mask if None).

    Returns:
        pydicom FileDataset ready for save_dicom() or direct streaming.
    """
    import io
    from pydicom.sequence import Sequence

    depth, height, width = mask_3d.shape
    if rows is None:
        rows = height
    if columns is None:
        columns = width

    # Generate UIDs
    sop_instance_uid = generate_uid()
    if not study_instance_uid:
        study_instance_uid = generate_uid()
    if not series_instance_uid:
        series_instance_uid = generate_uid()

    # Create file meta
    file_meta = create_file_meta(
        sop_class_uid=SEGMENTATION_STORAGE_UID,
        transfer_syntax_uid='1.2.840.10008.1.2.1',  # Explicit VR Little Endian
    )

    # Create dataset
    ds = FileDataset('', {}, file_meta=file_meta, preamble=b'\x00' * 128)
    ds.is_little_endian = True
    ds.is_implicit_VR = False

    # Patient Module
    ds.PatientName = patient_name
    ds.PatientID = patient_id

    # General Study Module
    ds.StudyInstanceUID = study_instance_uid
    ds.StudyDate = datetime.now().strftime('%Y%m%d')
    ds.StudyTime = datetime.now().strftime('%H%M%S')
    ds.StudyDescription = study_description
    ds.AccessionNumber = ''

    # General Series Module
    ds.Modality = 'SEG'
    ds.SeriesInstanceUID = series_instance_uid
    ds.SeriesNumber = 99
    ds.SeriesDescription = series_description

    # SOP Common Module
    ds.SOPClassUID = SEGMENTATION_STORAGE_UID
    ds.SOPInstanceUID = sop_instance_uid
    ds.InstanceCreationDate = ds.StudyDate
    ds.InstanceCreationTime = ds.StudyTime

    # Frame of Reference Module
    ds.FrameOfReferenceUID = generate_uid()
    ds.PositionReferenceIndicator = ''

    # General Equipment Module
    ds.Manufacturer = 'MSTool-AI'
    ds.ManufacturerModelName = 'MSTool-AI Segmentation'
    ds.SoftwareVersions = '2.0'

    # Image Pixel Module
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = 'MONOCHROME2'
    ds.Rows = rows
    ds.Columns = columns
    ds.BitsAllocated = 1
    ds.BitsStored = 1
    ds.HighBit = 0
    ds.PixelRepresentation = 0
    ds.LossyImageCompression = '00'

    # Segmentation Module
    ds.SegmentationType = 'BINARY'
    ds.ContentCreatorName = 'MSTool-AI'
    ds.ContentLabel = 'SEGMENTATION'
    ds.ContentDescription = series_description

    # Build SegmentSequence — one entry per label
    active_labels = [l for l in labels if l.get('id', 0) != 0]
    segment_sequence = []

    for label in active_labels:
        seg_item = Dataset()
        seg_item.SegmentNumber = label['id']
        seg_item.SegmentLabel = label.get('name', f'Label {label["id"]}')
        seg_item.SegmentAlgorithmType = 'SEMIAUTOMATIC'
        seg_item.SegmentAlgorithmName = 'MSTool-AI'

        # Segmented Property Category — Tissue
        cat = Dataset()
        cat.CodeValue = 'T-D0050'
        cat.CodingSchemeDesignator = 'SRT'
        cat.CodeMeaning = 'Tissue'
        seg_item.SegmentedPropertyCategoryCodeSequence = Sequence([cat])

        # Segmented Property Type — Lesion
        prop = Dataset()
        prop.CodeValue = 'M-01000'
        prop.CodingSchemeDesignator = 'SRT'
        prop.CodeMeaning = 'Morphologically Abnormal Structure'
        seg_item.SegmentedPropertyTypeCodeSequence = Sequence([prop])

        # Recommended Display Color (from label hex color)
        color_hex = label.get('color', '#FF0000')
        try:
            r = int(color_hex[1:3], 16)
            g = int(color_hex[3:5], 16)
            b = int(color_hex[5:7], 16)
            seg_item.RecommendedDisplayCIELabValue = [
                int(r * 100 / 255),  # Approximate L*
                int((r - 128)),       # Approximate a*
                int((b - 128)),       # Approximate b*
            ]
        except (ValueError, IndexError):
            pass

        segment_sequence.append(seg_item)

    ds.SegmentSequence = Sequence(segment_sequence)

    # Number of Frames
    num_frames = depth * len(active_labels)
    ds.NumberOfFrames = num_frames

    # Per-Frame Functional Groups Sequence
    per_frame_seq = []
    frame_data_list = []

    for slice_idx in range(depth):
        for label in active_labels:
            # Frame Content
            frame_content = Dataset()
            frame_content.DimensionIndexValues = [label['id'], slice_idx + 1]

            # Segment Identification
            seg_id = Dataset()
            seg_id.ReferencedSegmentNumber = label['id']

            # Plane Position
            plane_pos = Dataset()
            plane_pos.ImagePositionPatient = [0.0, 0.0, float(slice_idx)]

            # Build per-frame item
            pf_item = Dataset()
            pf_item.FrameContentSequence = Sequence([frame_content])
            pf_item.SegmentIdentificationSequence = Sequence([seg_id])
            pf_item.PlanePositionSequence = Sequence([plane_pos])
            per_frame_seq.append(pf_item)

            # Extract binary frame: 1 where mask == label_id, 0 elsewhere
            binary_slice = (mask_3d[slice_idx] == label['id']).astype(np.uint8)
            frame_data_list.append(binary_slice)

    ds.PerFrameFunctionalGroupsSequence = Sequence(per_frame_seq)

    # Shared Functional Groups
    shared = Dataset()

    # Plane Orientation
    plane_orient = Dataset()
    plane_orient.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    shared.PlaneOrientationSequence = Sequence([plane_orient])

    # Pixel Measures
    pixel_measures = Dataset()
    pixel_measures.PixelSpacing = [1.0, 1.0]
    pixel_measures.SliceThickness = 1.0
    pixel_measures.SpacingBetweenSlices = 1.0
    shared.PixelMeasuresSequence = Sequence([pixel_measures])

    ds.SharedFunctionalGroupsSequence = Sequence([shared])

    # Pack binary pixel data — bit-packed (8 pixels per byte)
    all_frames = np.concatenate([f.flatten() for f in frame_data_list])
    # Pad to multiple of 8
    padded_len = ((len(all_frames) + 7) // 8) * 8
    padded = np.zeros(padded_len, dtype=np.uint8)
    padded[:len(all_frames)] = all_frames
    # Pack bits
    packed = np.packbits(padded, bitorder='little')
    ds.PixelData = packed.tobytes()

    return ds
