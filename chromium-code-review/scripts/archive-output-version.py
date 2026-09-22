#!/usr/bin/env python3
"""Preserve exact prior output bytes authenticated by an existing input manifest."""
import argparse
from pathlib import Path
from input_accounting import mutable_output
from orchestration_state import INPUT_COLUMNS, digest, fail, guard, read_rows, require_review_dir

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('review_dir', type=Path)
parser.add_argument('artifact', type=Path)
parser.add_argument('historical_bytes', type=Path)
args = parser.parse_args()
root = require_review_dir(args.review_dir)
artifact = args.artifact.resolve()
if not mutable_output(root, artifact):
    fail('only final-output fragment or coverage-row history may be archived')
payload = args.historical_bytes.read_bytes()
sha = digest(payload)
with guard(root):
    rows = read_rows(root / 'input-manifest.tsv', INPUT_COLUMNS)
    matches = [row for row in rows if Path(row['input_path']).resolve() == artifact
               and row['sha256'] == sha and row['bytes'] == str(len(payload))]
    if not matches:
        fail('historical bytes do not match any existing manifest binding for this output')
    destination = root / 'output-history' / (sha + '.bin')
    destination.parent.mkdir(exist_ok=True)
    if destination.exists() and destination.read_bytes() != payload:
        fail('existing content-addressed archive differs')
    if not destination.exists():
        with destination.open('xb') as stream:
            stream.write(payload)
    destination.chmod(0o444)
    print(destination)
