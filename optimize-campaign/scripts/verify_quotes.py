#!/usr/bin/env python3
"""Verify the quotes in a prose deliverable against the files they cite.

Usage: verify_quotes.py <campaign dir> <document.md>

A quote is a fenced code block preceded (within three lines) by
`sed -n 'A,Bp' <path>`; every non-blank line of the block, with leading
diff markers and whitespace normalized, must appear inside lines A-B of
<path> (resolved against the campaign dir). `...` lines are elisions and
are allowed. Exit status 1 when any quoted line is not in its range. A
document that fails is not read (END-OF-CAMPAIGN-CHANGES item 39).
"""
import pathlib
import re
import sys

MARK = re.compile(r"sed -n '(\d+),(\d+)p' (\S+)[^\n]*\n(?:[^\n]*\n){0,3}?```[a-z]*\n(.*?)```", re.S)


def norm(line):
    return re.sub(r"\s+", " ", line.lstrip("+- ").strip())


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    campaign, doc = pathlib.Path(argv[1]), pathlib.Path(argv[2])
    text = doc.read_text()
    blocks = MARK.findall(text)
    if not blocks:
        print(f"{doc}: no quoted blocks with `sed -n 'A,Bp' <file>` markers found")
        return 1
    bad = 0
    for a, b, path, body in blocks:
        target = campaign / path
        if not target.is_file():
            print(f"FAIL {path}:{a}-{b}: file not found under {campaign}")
            bad += 1
            continue
        lines = target.read_text(errors="replace").split("\n")
        window = " ".join(norm(l) for l in lines[int(a) - 1:int(b)] if norm(l))
        quoted = [norm(l) for l in body.split("\n") if norm(l) and norm(l) != "..."]
        missing = [q for q in quoted if q not in window]
        if missing:
            bad += 1
            print(f"FAIL {path}:{a}-{b}: {len(missing)} of {len(quoted)} quoted lines are not in that range:")
            for q in missing:
                print(f"     {q[:140]}")
        else:
            print(f"ok   {path}:{a}-{b}: {len(quoted)} lines")
    print(f"{len(blocks)} quoted block(s), {bad} failing")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
