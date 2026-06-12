# app/scripts/bin_2_base64_splitter.py
# -*- coding: utf-8 -*-
"""
Binary to Base64 Splitter
Splits binary file into chunks and saves as Base64 files
Usage: python splitter.py <input_file> [chunk_size_kb] [output_dir]
"""

import os
import base64
import sys
import argparse
from pathlib import Path


def split_file_to_base64(input_file, chunk_size_kb=5, output_dir=None):
    """
    Split binary file into Base64 chunks

    Args:
        input_file: Path to input binary file
        chunk_size_kb: Chunk size in kilobytes (default: 5)
        output_dir: Output directory (default: same as input file)
    """
    # Convert KB to bytes
    chunk_size_bytes = chunk_size_kb * 1024

    # Get file info
    input_path = Path(input_file)
    if not input_path.exists():
        print(f"Error: File '{input_file}' not found!")
        return False

    # Create output directory
    if output_dir is None:
        output_dir = input_path.parent / f"{input_path.stem}_chunks"
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Get base filename without extension
    base_name = input_path.stem

    # Read binary file
    print(f"Reading file: {input_path.name}")
    with open(input_file, 'rb') as f:
        file_data = f.read()

    file_size = len(file_data)
    total_chunks = (file_size + chunk_size_bytes - 1) // chunk_size_bytes

    print(f"File size: {file_size:,} bytes ({file_size / 1024:.2f} KB)")
    print(f"Chunk size: {chunk_size_kb} KB")
    print(f"Total chunks: {total_chunks}")
    print(f"Output directory: {output_dir}")
    print()

    # Split and encode
    for i in range(total_chunks):
        start = i * chunk_size_bytes
        end = min(start + chunk_size_bytes, file_size)
        chunk_data = file_data[start:end]

        # Encode to Base64
        base64_data = base64.b64encode(chunk_data).decode('ascii')

        # Save to file
        output_file = output_dir / f"{i + 1}.{base_name}.txt"
        with open(output_file, 'w', encoding='ascii') as f:
            f.write(base64_data)

        print(f"Created: {output_file.name} ({len(chunk_data):,} bytes)")

        # Progress indicator
        if (i + 1) % 10 == 0 or (i + 1) == total_chunks:
            print(f"Progress: {i + 1}/{total_chunks} chunks ({((i + 1) / total_chunks) * 100:.1f}%)")

    print(f"\n✅ COMPLETED! Created {total_chunks} files in: {output_dir}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Split binary file into Base64 chunks',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python splitter.py document.pdf
  python splitter.py video.mp4 10
  python splitter.py file.exe 5 C:/output/folder
        """
    )

    parser.add_argument('input_file', help='Input binary file path')
    parser.add_argument('chunk_size', nargs='?', type=int, default=5,
                        help='Chunk size in KB (default: 5)')
    parser.add_argument('output_dir', nargs='?', default=None,
                        help='Output directory (default: input_file_stem_chunks)')

    args = parser.parse_args()

    split_file_to_base64(args.input_file, args.chunk_size, args.output_dir)


if __name__ == "__main__":
    main()