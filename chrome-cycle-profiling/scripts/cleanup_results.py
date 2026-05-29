#!/usr/bin/env python3
# Copyright 2026 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import shutil
import sys

CWD = "/usr/local/google/home/pmeenan/src/chromium/src"
DIRS_TO_CLEAN = [
    "scratch/results_probes",
    "scratch/results_ab_enabled",
    "scratch/results_ab_disabled"
]

def main():
    print("=== CLEANING UP CROSSBENCH SCRATCH DIRECTORIES ===")
    cleaned_any = False
    for d in DIRS_TO_CLEAN:
        full_path = os.path.join(CWD, d)
        if os.path.exists(full_path):
            print(f"Removing directory: {d}")
            try:
                shutil.rmtree(full_path)
                cleaned_any = True
            except Exception as e:
                print(f"Error removing {d}: {e}", file=sys.stderr)
    if not cleaned_any:
        print("No temporary scratch directories found. Workspace is already clean.")
    else:
        print("Cleanup complete.")

if __name__ == "__main__":
    main()
