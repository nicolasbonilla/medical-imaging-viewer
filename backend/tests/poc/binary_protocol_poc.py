"""
Proof of Concept: Binary Protocol vs Base64 Encoding

This script validates that binary transfer is significantly faster
and uses less bandwidth than Base64 encoding.

Expected Results:
- Binary: 3-5x faster than Base64
- Binary: 33% smaller than Base64
"""

import numpy as np
import base64
import time
from typing import Tuple, Dict


def generate_test_slice(rows: int = 512, cols: int = 512) -> np.ndarray:
    """Generate a synthetic medical image slice (grayscale uint8)."""
    return np.random.randint(0, 256, (rows, cols), dtype=np.uint8)


def benchmark_base64_encoding(slice_data: np.ndarray) -> Tuple[float, int]:
    """
    Benchmark Base64 encoding (current method).

    Returns: (time_ms, size_bytes)
    """
    start = time.perf_counter()
    base64_encoded = base64.b64encode(slice_data.tobytes()).decode('utf-8')
    elapsed_ms = (time.perf_counter() - start) * 1000
    size_bytes = len(base64_encoded)

    return elapsed_ms, size_bytes


def benchmark_binary_transfer(slice_data: np.ndarray) -> Tuple[float, int]:
    """
    Benchmark binary transfer (proposed method).

    Returns: (time_ms, size_bytes)
    """
    start = time.perf_counter()
    binary_data = slice_data.tobytes()
    elapsed_ms = (time.perf_counter() - start) * 1000
    size_bytes = len(binary_data)

    return elapsed_ms, size_bytes


def run_poc(rows: int = 512, cols: int = 512, iterations: int = 100) -> Dict:
    """
    Run Proof of Concept with multiple iterations.

    Args:
        rows: Image height
        cols: Image width
        iterations: Number of test iterations for averaging

    Returns:
        Dictionary with benchmark results
    """
    print("=" * 70)
    print("PROOF OF CONCEPT: Binary Protocol vs Base64 Encoding")
    print("=" * 70)
    print(f"\nTest Configuration:")
    print(f"  Image Size: {rows}x{cols} pixels")
    print(f"  Data Type: uint8 (grayscale)")
    print(f"  Iterations: {iterations}")
    print(f"  Total Pixels: {rows * cols:,}")
    print()

    # Generate test data
    slice_data = generate_test_slice(rows, cols)

    # Benchmark Base64
    base64_times = []
    base64_sizes = []

    print("Running Base64 benchmarks...", end=" ", flush=True)
    for _ in range(iterations):
        time_ms, size_bytes = benchmark_base64_encoding(slice_data)
        base64_times.append(time_ms)
        base64_sizes.append(size_bytes)
    print("OK")

    # Benchmark Binary
    binary_times = []
    binary_sizes = []

    print("Running Binary benchmarks...", end=" ", flush=True)
    for _ in range(iterations):
        time_ms, size_bytes = benchmark_binary_transfer(slice_data)
        binary_times.append(time_ms)
        binary_sizes.append(size_bytes)
    print("OK")

    # Calculate statistics
    base64_avg_time = np.mean(base64_times)
    base64_std_time = np.std(base64_times)
    base64_avg_size = np.mean(base64_sizes)

    binary_avg_time = np.mean(binary_times)
    binary_std_time = np.std(binary_times)
    binary_avg_size = np.mean(binary_sizes)

    speedup = base64_avg_time / binary_avg_time if binary_avg_time > 0 else 0
    size_reduction = (1 - binary_avg_size / base64_avg_size) * 100 if base64_avg_size > 0 else 0

    # Print results
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)

    print("\n[BASE64 ENCODING - Current Method]")
    print(f"  Average Time:  {base64_avg_time:.4f} ms (+-{base64_std_time:.4f} ms)")
    print(f"  Size:          {base64_avg_size:,.0f} bytes ({base64_avg_size/1024:.2f} KB)")
    print(f"  Throughput:    {(rows * cols) / (base64_avg_time / 1000) / 1_000_000:.2f} Mpixels/sec")

    print("\n[BINARY TRANSFER - Proposed Method]")
    print(f"  Average Time:  {binary_avg_time:.4f} ms (+-{binary_std_time:.4f} ms)")
    print(f"  Size:          {binary_avg_size:,.0f} bytes ({binary_avg_size/1024:.2f} KB)")
    print(f"  Throughput:    {(rows * cols) / (binary_avg_time / 1000) / 1_000_000:.2f} Mpixels/sec")

    print("\n[PERFORMANCE IMPROVEMENT]")
    print(f"  Speedup:       {speedup:.2f}x faster")
    print(f"  Size Reduction: {size_reduction:.1f}% smaller")
    print(f"  Time Saved:    {base64_avg_time - binary_avg_time:.4f} ms per slice")

    # Validation
    print("\n[VALIDATION]")
    if speedup >= 3.0:
        print(f"  Speed:  PASS (>= 3x speedup achieved: {speedup:.2f}x)")
    else:
        print(f"  Speed:  WARNING (Expected >= 3x, got {speedup:.2f}x)")

    if size_reduction >= 30:
        print(f"  Size:   PASS (>= 30% reduction achieved: {size_reduction:.1f}%)")
    else:
        print(f"  Size:   WARNING (Expected >= 30%, got {size_reduction:.1f}%)")

    print("\n" + "=" * 70)

    # Return results for programmatic use
    return {
        "base64": {
            "avg_time_ms": base64_avg_time,
            "std_time_ms": base64_std_time,
            "size_bytes": base64_avg_size,
        },
        "binary": {
            "avg_time_ms": binary_avg_time,
            "std_time_ms": binary_std_time,
            "size_bytes": binary_avg_size,
        },
        "improvement": {
            "speedup": speedup,
            "size_reduction_percent": size_reduction,
            "time_saved_ms": base64_avg_time - binary_avg_time,
        },
        "validation": {
            "speed_pass": speedup >= 3.0,
            "size_pass": size_reduction >= 30,
        }
    }


def test_different_sizes():
    """Test with different image sizes (typical medical imaging dimensions)."""
    test_cases = [
        (256, 256, "MRI Small"),
        (512, 512, "CT Standard"),
        (1024, 1024, "CT High-Res"),
    ]

    print("\n" + "=" * 70)
    print("TESTING DIFFERENT IMAGE SIZES")
    print("=" * 70)

    all_results = []

    for rows, cols, name in test_cases:
        print(f"\n\n{'=' * 70}")
        print(f"Test Case: {name} ({rows}x{cols})")
        print('=' * 70)

        results = run_poc(rows, cols, iterations=50)
        results["name"] = name
        results["dimensions"] = (rows, cols)
        all_results.append(results)

    # Summary
    print("\n\n" + "=" * 70)
    print("SUMMARY ACROSS ALL IMAGE SIZES")
    print("=" * 70)

    print(f"\n{'Image Size':<20} {'Speedup':<12} {'Size Reduction':<18} {'Status'}")
    print("-" * 70)

    for result in all_results:
        name = result["name"]
        speedup = result["improvement"]["speedup"]
        reduction = result["improvement"]["size_reduction_percent"]
        status = "PASS" if result["validation"]["speed_pass"] and result["validation"]["size_pass"] else "WARN"

        print(f"{name:<20} {speedup:>6.2f}x      {reduction:>6.1f}%             {status}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    # Run standard test (512x512)
    results = run_poc(rows=512, cols=512, iterations=100)

    # Test different sizes
    test_different_sizes()

    # Final recommendation
    print("\n[RECOMMENDATION]")
    print("=" * 70)

    if results["validation"]["speed_pass"] and results["validation"]["size_pass"]:
        print("[SUCCESS] Binary protocol shows significant improvement over Base64.")
        print("[SUCCESS] Proceed with FASE 2 implementation (WebSocket + Binary).")
        print()
        print("Expected benefits in production:")
        print(f"  - {results['improvement']['speedup']:.1f}x faster slice loading")
        print(f"  - {results['improvement']['size_reduction_percent']:.0f}% bandwidth reduction")
        print(f"  - ~{results['improvement']['time_saved_ms']:.2f}ms saved per slice")
        print()
        print("For a typical session (100 slices):")
        print(f"  - Time saved: ~{results['improvement']['time_saved_ms'] * 100 / 1000:.1f} seconds")
        print(f"  - Bandwidth saved: ~{(results['base64']['size_bytes'] - results['binary']['size_bytes']) * 100 / 1024 / 1024:.1f} MB")
    else:
        print("[WARNING] Binary protocol did not meet expected improvement thresholds.")
        print("[WARNING] Review implementation before proceeding to FASE 2.")

    print("=" * 70)
