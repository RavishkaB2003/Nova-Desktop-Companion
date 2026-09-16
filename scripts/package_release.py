#!/usr/bin/env python3
"""
scripts/package_release.py - Project NOVA Standalone Windows Packaging Script

Automates:
1. PyInstaller compilation using nova.spec.
2. Verification of binary, vector assets, and Vosk acoustic model files.
3. Creation of portable distribution zip: NOVA-Desktop-Companion-v1.0.0-win64.zip.
4. SHA-256 cryptographic checksum calculation and output to SHA256SUMS.txt.
"""

import hashlib
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


def calculate_sha256(filepath: Path) -> str:
    """Compute SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_file_size_mb(filepath: Path) -> float:
    """Return file size in megabytes."""
    return filepath.stat().st_size / (1024 * 1024)


def get_dir_size_mb(dirpath: Path) -> float:
    """Return total directory size in megabytes."""
    total = 0
    for p in dirpath.rglob("*"):
        if p.is_file():
            total += p.stat().st_size
    return total / (1024 * 1024)


def main() -> int:
    print("=" * 70)
    print("Project NOVA - Standalone Windows x64 Release Packaging")
    print("=" * 70)

    project_root = Path(__file__).resolve().parent.parent
    os.chdir(project_root)
    print(f"[*] Workspace Root: {project_root}")

    dist_dir = project_root / "dist"
    build_dir = project_root / "build"
    nova_dist = dist_dir / "nova"
    exe_path = nova_dist / "nova.exe"
    zip_output = dist_dir / "NOVA-Desktop-Companion-v1.0.0-win64.zip"
    sha_file = dist_dir / "SHA256SUMS.txt"

    # Step 1: Clean previous build artifacts
    print("\n[1/5] Cleaning previous distribution targets...")
    if nova_dist.exists():
        print(f"    Removing {nova_dist}...")
        shutil.rmtree(nova_dist)
    if zip_output.exists():
        print(f"    Removing {zip_output}...")
        zip_output.unlink()
    if sha_file.exists():
        print(f"    Removing {sha_file}...")
        sha_file.unlink()

    # Step 2: Run PyInstaller
    print("\n[2/5] Running PyInstaller with nova.spec...")
    cmd = [sys.executable, "-m", "PyInstaller", "nova.spec", "--clean", "--noconfirm"]
    print(f"    Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=project_root)
    if result.returncode != 0:
        print(f"\n[!] PyInstaller build failed with return code {result.returncode}")
        return result.returncode

    # Step 3: Verify build integrity
    print("\n[3/5] Verifying bundle contents...")
    if not exe_path.exists():
        print(f"[!] Error: Executable not found at {exe_path}")
        return 1
    print(f"    [OK] Executable found: {exe_path} ({get_file_size_mb(exe_path):.2f} MB)")

    # Verify assets in root or _internal
    asset_found = False
    for p in [nova_dist / "assets" / "mascot" / "mascot_sleeping.svg",
              nova_dist / "_internal" / "assets" / "mascot" / "mascot_sleeping.svg"]:
        if p.exists():
            asset_found = True
            print(f"    [OK] Mascot SVG assets verified at: {p.parent}")
            break
    if not asset_found:
        print("[!] Error: Mascot vector assets were not bundled into the distribution directory!")
        return 1

    # Verify Vosk acoustic model in root or _internal
    model_found = False
    for p in [nova_dist / "models" / "vosk-model-small-en-us-0.15" / "am" / "final.mdl",
              nova_dist / "_internal" / "models" / "vosk-model-small-en-us-0.15" / "am" / "final.mdl"]:
        if p.exists():
            model_found = True
            print(f"    [OK] Vosk Kaldi model verified at: {p.parent.parent}")
            break
    if not model_found:
        print("[!] Error: Vosk speech model was not bundled into the distribution directory!")
        return 1

    total_bundle_size = get_dir_size_mb(nova_dist)
    print(f"    Total uncompressed bundle size: {total_bundle_size:.2f} MB")

    # Step 4: Create portable zip distribution
    print("\n[4/5] Creating portable ZIP archive...")
    print(f"    Destination: {zip_output}")
    with zipfile.ZipFile(zip_output, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for file in nova_dist.rglob("*"):
            if file.is_file():
                rel_path = file.relative_to(dist_dir)
                zf.write(file, arcname=str(rel_path))

    zip_size = get_file_size_mb(zip_output)
    print(f"    [OK] Portable zip created: {zip_size:.2f} MB")

    # Step 5: Calculate SHA-256 and write checksums
    print("\n[5/5] Computing cryptographic SHA-256 checksums...")
    exe_hash = calculate_sha256(exe_path)
    zip_hash = calculate_sha256(zip_output)

    checksum_lines = [
        f"{exe_hash}  nova/nova.exe\n",
        f"{zip_hash}  NOVA-Desktop-Companion-v1.0.0-win64.zip\n",
    ]
    with open(sha_file, "w", encoding="utf-8") as f:
        f.writelines(checksum_lines)

    print(f"    [OK] Checksums written to {sha_file}")
    print("\n" + "=" * 70)
    print("RELEASE PACKAGING COMPLETE")
    print("=" * 70)
    print(f"Executable:  {exe_path} ({get_file_size_mb(exe_path):.2f} MB)")
    print(f"SHA-256:     {exe_hash}")
    print("-" * 70)
    print(f"Archive:     {zip_output} ({zip_size:.2f} MB)")
    print(f"SHA-256:     {zip_hash}")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
