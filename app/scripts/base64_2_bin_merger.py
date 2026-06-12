# app/scripts/base64_2_bin_merger.py

# -*- coding: utf-8 -*-
"""
Base64 to Binary Merger
Merges Base64 chunks back into original binary file
Usage: python merger.py <input_directory> <base_filename>
"""

import os
import base64
import sys
import re
import argparse
from pathlib import Path


def merge_base64_to_binary(input_dir, base_filename, output_dir=None):
    """
    Merge Base64 chunks into binary file

    Args:
        input_dir: Directory containing Base64 chunks
        base_filename: Base filename (without number and extension)
        output_dir: Output directory (default: input_dir/decode)
    """
    input_path = Path(input_dir)
    if not input_path.exists():
        print(f"Error: Directory '{input_dir}' not found!")
        return False

    # Find all matching chunk files
    pattern = re.compile(rf'^(\d+)\.{re.escape(base_filename)}\.txt$')
    chunk_files = []

    for file in input_path.iterdir():
        if file.is_file():
            match = pattern.match(file.name)
            if match:
                chunk_number = int(match.group(1))
                chunk_files.append((chunk_number, file))

    if not chunk_files:
        print(f"Error: No chunks found for base filename '{base_filename}'")
        print(f"Expected pattern: N.{base_filename}.txt")
        print(f"Searched in: {input_path.absolute()}")
        return False

    # Sort by chunk number
    chunk_files.sort(key=lambda x: x[0])

    print(f"Found {len(chunk_files)} chunks:")
    for number, file in chunk_files:
        print(f"  {number}: {file.name}")
    print()

    # Create output directory
    if output_dir is None:
        output_dir = input_path / 'decode'
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Output file path
    output_file = output_dir / f"{base_filename}.bin"

    # Merge and decode chunks
    print(f"Merging chunks to: {output_file}")

    total_size = 0
    with open(output_file, 'wb') as out_file:
        for i, (number, chunk_file) in enumerate(chunk_files, 1):
            # Read Base64 content
            with open(chunk_file, 'r', encoding='ascii') as f:
                base64_content = f.read().strip()

            # Decode from Base64
            try:
                decoded_data = base64.b64decode(base64_content)
            except Exception as e:
                print(f"Error decoding {chunk_file.name}: {e}")
                return False

            # Write to output file
            out_file.write(decoded_data)
            total_size += len(decoded_data)

            print(f"Processed: {chunk_file.name} ({len(decoded_data):,} bytes)")

            # Progress indicator
            if i % 10 == 0 or i == len(chunk_files):
                print(f"Progress: {i}/{len(chunk_files)} chunks ({((i) / len(chunk_files)) * 100:.1f}%)")

    # Verify file size
    output_size = output_file.stat().st_size

    print()
    print(f"✅ COMPLETED!")
    print(f"   Fragments: {len(chunk_files)}")
    print(f"   Total size: {total_size:,} bytes ({total_size / 1024:.2f} KB)")
    print(f"   Output file: {output_file}")
    print(f"   File size: {output_size:,} bytes ({output_size / 1024:.2f} KB)")

    return True


def main():
    parser = argparse.ArgumentParser(
        description='Merge Base64 chunks into binary file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python merger.py ./chunks document
  python merger.py C:/output/video_chunks video
  python merger.py ./chunks document C:/restored
        """
    )

    parser.add_argument('input_dir', help='Directory with Base64 chunks')
    parser.add_argument('base_filename', help='Base filename (without number and extension)')
    parser.add_argument('output_dir', nargs='?', default=None,
                        help='Output directory (default: input_dir/decode)')

    args = parser.parse_args()

    merge_base64_to_binary(args.input_dir, args.base_filename, args.output_dir)


if __name__ == "__main__":
    main()