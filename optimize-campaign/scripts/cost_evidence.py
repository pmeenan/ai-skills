#!/usr/bin/env python3
"""Cost packets: where a row's time goes, from the story's cycle profile.

A redundancy packet says how much of a row's time is a skip or a reuse. When
it says none (the row closes by count) and the row is still large, the
question left is the Layer 3/4 one: which loop, walk or leaf carries the
time, and would a different algorithm do less of it. That claim is a cost
claim, and it is bounded by the profile: the fraction of the row's time in
the frames the new algorithm would avoid. This module reduces the story's
`profile.collapsed` into that bound, the same way `redundancy_evidence.py`
reduces a probe log, so `decompose` can re-derive it.

    python3 cost_evidence.py --collapsed <profile.collapsed> [--collapsed ...] \
        --anchor '<exact frame of the row>' --target-story <story> \
        --profile-id <id> --out <campaign>/evidence/cost_<key>.json

The packet lists, for samples carrying the anchor, the time by direct child
frame and by leaf (self-time) frame, each as a share of the story and a
fraction of the row. An `algorithmic` row names `avoided_frames` from these
lists; its `estimated_avoidable_fraction` may not exceed their summed
fraction of the row.
"""
import argparse
import hashlib
import json
import pathlib
import sys

SCHEMA_VERSION = 1
TOP_ENTRIES = 40


class CostError(ValueError):
    pass


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def reduce_stacks(collapsed_files, anchor, top=TOP_ENTRIES):
    total = 0.0
    row = 0.0
    children = {}
    leaves = {}
    for path in collapsed_files:
        with open(path, errors="replace") as handle:
            for line in handle:
                stack, _, weight = line.rstrip("\n").rpartition(" ")
                try:
                    weight = float(weight)
                except ValueError:
                    continue
                total += weight
                frames = stack.split(";")
                if anchor not in frames:
                    continue
                row += weight
                index = len(frames) - 1 - frames[::-1].index(anchor)
                child = frames[index + 1] if index + 1 < len(frames) else "(self)"
                children[child] = children.get(child, 0.0) + weight
                leaves[frames[-1]] = leaves.get(frames[-1], 0.0) + weight
    if total <= 0:
        raise CostError("no samples in the collapsed stacks")
    if row <= 0:
        raise CostError(f"anchor {anchor!r} carries no samples in the collapsed stacks")

    def table(bucket):
        items = sorted(bucket.items(), key=lambda kv: -kv[1])[:top]
        return [{"frame": frame, "share_pct": round(100.0 * w / total, 4),
                 "fraction_of_row": round(w / row, 6)} for frame, w in items]

    return {
        "row_share_pct": round(100.0 * row / total, 4),
        "row_weight": row,
        "total_weight": total,
        "children": table(children),
        "leaves": table(leaves),
    }


def build_cost_packet(collapsed_files, anchor, target_story, profile_id=None, top=TOP_ENTRIES):
    files = [pathlib.Path(p) for p in collapsed_files]
    for path in files:
        if not path.is_file():
            raise CostError(f"collapsed stacks not found: {path}")
    summary = reduce_stacks(files, anchor, top)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "cost-evidence",
        "anchor": anchor,
        "target_story": target_story,
        "profile_id": profile_id,
        "sources": [{"path": str(p.resolve()), "sha256": sha256_file(p)} for p in files],
        **summary,
    }


def load_cost_packet(path):
    try:
        packet = json.loads(pathlib.Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise CostError(f"cannot read cost packet {path}: {exc}") from exc
    if not isinstance(packet, dict) or packet.get("kind") != "cost-evidence":
        raise CostError(f"{path} is not a cost evidence packet")
    if packet.get("schema_version") != SCHEMA_VERSION:
        raise CostError(f"{path}: unsupported cost packet schema")
    for field in ("anchor", "target_story", "sources", "row_share_pct", "children", "leaves"):
        if field not in packet:
            raise CostError(f"{path}: cost packet lacks {field}")
    return packet


def frame_matches(frame, prefix):
    prefix = prefix.rstrip("(").rstrip()
    return frame == prefix or frame.startswith(prefix + "(") or frame == "(self)" and prefix == "(self)"


def avoided_fraction(packet, avoided_frames):
    """Fraction of the row's time in the named frames: each name matches
    direct children first (inclusive), else leaves (self time). Returns the
    capped sum and the names that matched nothing."""
    total = 0.0
    unmatched = []
    for name in avoided_frames:
        found = [e["fraction_of_row"] for e in packet["children"] if frame_matches(e["frame"], name)]
        if not found:
            found = [e["fraction_of_row"] for e in packet["leaves"] if frame_matches(e["frame"], name)]
        if not found:
            unmatched.append(name)
        total += sum(found)
    return min(total, 1.0), unmatched


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--collapsed", type=pathlib.Path, action="append", required=True)
    parser.add_argument("--anchor", required=True, help="exact frame text of the row's anchor")
    parser.add_argument("--target-story", required=True)
    parser.add_argument("--profile-id", default=None)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    parser.add_argument("--top", type=int, default=TOP_ENTRIES)
    args = parser.parse_args(argv)
    try:
        packet = build_cost_packet(args.collapsed, args.anchor, args.target_story, args.profile_id, args.top)
    except CostError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"anchor": packet["anchor"], "row_share_pct": packet["row_share_pct"],
                      "children": packet["children"][:5], "leaves": packet["leaves"][:5], "out": str(args.out)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
