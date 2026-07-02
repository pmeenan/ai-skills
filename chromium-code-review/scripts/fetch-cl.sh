#!/usr/bin/env bash
# fetch-cl.sh — fetch and pin a Chromium CL patchset for review.
#
# Usage: fetch-cl.sh <cl-number> [patchset] [review-dir]
#
#   <cl-number>   Gerrit change number, e.g. 7997557
#   [patchset]    patchset to materialize ("current" or a number; default
#                 current). Follow-up reviews call this twice: once for the
#                 current patchset, once for the prior reviewed one.
#   [review-dir]  directory for pin.md/detail.json/comments.json/worktree
#                 (default: ${TMPDIR:-/tmp}/cl-<cl>-ps<ps>)
#
# Environment overrides:
#   CHROMIUM_SRC    repo root (default: git rev-parse --show-toplevel of cwd)
#   GERRIT_HOST     default https://chromium-review.googlesource.com
#   GERRIT_PROJECT  default chromium/src
#
# Enforces the skill's pinning rules mechanically:
#   - metadata fetched with ALL_REVISIONS (+ published comments), XSSI-stripped
#   - the worktree is created detached at the explicit revision SHA — never
#     FETCH_HEAD — with fetch, add, and verify as separate steps
#   - `rev-parse HEAD` is verified against the pinned SHA before returning
#
# The worktree is read-only with respect to the review. Remove it when done:
#   git -C <repo> worktree remove <review-dir>/worktree

set -u

die() { echo "fetch-cl.sh: ERROR: $*" >&2; exit 1; }

CL="${1:-}"
[[ "$CL" =~ ^[0-9]+$ ]] || die "usage: fetch-cl.sh <cl-number> [patchset] [review-dir]"
REQ_PS="${2:-current}"
[[ "$REQ_PS" == "current" || "$REQ_PS" =~ ^[0-9]+$ ]] || die "patchset must be a number or 'current'"

GERRIT_HOST="${GERRIT_HOST:-https://chromium-review.googlesource.com}"
GERRIT_PROJECT="${GERRIT_PROJECT:-chromium/src}"
PROJECT_ENC="${GERRIT_PROJECT//\//%2F}"

command -v curl >/dev/null 2>&1 || die "curl is required"
command -v python3 >/dev/null 2>&1 || die "python3 is required"

REPO="${CHROMIUM_SRC:-$(git rev-parse --show-toplevel 2>/dev/null || true)}"
[[ -n "$REPO" ]] || die "not inside a git checkout and CHROMIUM_SRC is not set"
git -C "$REPO" rev-parse --git-dir >/dev/null 2>&1 || die "$REPO is not a git checkout"

DETAIL_URL="$GERRIT_HOST/changes/$PROJECT_ENC~$CL/detail?o=ALL_REVISIONS&o=ALL_COMMITS&o=CURRENT_FILES&o=MESSAGES&o=DETAILED_ACCOUNTS"
COMMENTS_URL="$GERRIT_HOST/changes/$PROJECT_ENC~$CL/comments"

TMP_DETAIL="$(mktemp)" || die "mktemp failed"
TMP_COMMENTS="$(mktemp)" || die "mktemp failed"
trap 'rm -f "$TMP_DETAIL" "$TMP_COMMENTS"' EXIT

echo "Fetching change detail for CL $CL ..." >&2
curl -sfS --retry 3 --retry-delay 2 "$DETAIL_URL" -o "$TMP_DETAIL" \
  || die "failed to fetch change detail from $DETAIL_URL"

echo "Fetching published comments ..." >&2
if ! curl -sfS --retry 3 --retry-delay 2 "$COMMENTS_URL" -o "$TMP_COMMENTS"; then
  echo "fetch-cl.sh: WARNING: comments fetch failed; writing empty comments.json" >&2
  printf '{}' > "$TMP_COMMENTS"
fi

# Parse the detail JSON: resolve the requested patchset to its SHA and parent.
read -r PS SHA PARENT CURRENT_PS < <(python3 - "$TMP_DETAIL" "$REQ_PS" <<'PYEOF'
import json, sys

raw = open(sys.argv[1], 'rb').read()
if raw.startswith(b")]}'"):
    raw = raw.split(b'\n', 1)[1]
d = json.loads(raw)

revs = d['revisions']
current_sha = d['current_revision']
current_ps = revs[current_sha]['_number']
req = sys.argv[2]
ps = current_ps if req == 'current' else int(req)

sha = next((s for s, r in revs.items() if r['_number'] == ps), None)
if sha is None:
    available = sorted(r['_number'] for r in revs.values())
    sys.exit(f"patchset {ps} not found (available: {available})")

parents = revs[sha].get('commit', {}).get('parents', [])
parent = parents[0]['commit'] if parents else 'UNKNOWN'
print(ps, sha, parent, current_ps)
PYEOF
) || die "failed to parse change detail"

REVIEW_DIR="${3:-${TMPDIR:-/tmp}/cl-$CL-ps$PS}"
mkdir -p "$REVIEW_DIR/ledger" || die "cannot create $REVIEW_DIR"
mv "$TMP_DETAIL" "$REVIEW_DIR/detail.json"
mv "$TMP_COMMENTS" "$REVIEW_DIR/comments.json"
trap - EXIT

LAST2="$(printf '%02d' $((CL % 100)))"
REF="refs/changes/$LAST2/$CL/$PS"
WT="$REVIEW_DIR/worktree"

if [[ -e "$WT" ]]; then
  EXISTING="$(git -C "$WT" rev-parse HEAD 2>/dev/null || true)"
  if [[ "$EXISTING" == "$SHA" ]]; then
    echo "Worktree already materialized at $WT (HEAD matches pin)." >&2
  else
    die "$WT exists but HEAD ($EXISTING) != pinned SHA ($SHA); remove it first: git -C '$REPO' worktree remove '$WT'"
  fi
else
  # Step 1: fetch the ref. FETCH_HEAD gets written but is deliberately unused.
  echo "Fetching $REF ..." >&2
  git -C "$REPO" fetch "$GERRIT_HOST/$GERRIT_PROJECT" "$REF" || die "git fetch $REF failed"
  # Step 2: confirm the advertised SHA actually arrived.
  git -C "$REPO" cat-file -e "$SHA^{commit}" 2>/dev/null \
    || die "pinned SHA $SHA not present after fetch — refusing to guess"
  # Step 3: detached worktree at the explicit SHA — never FETCH_HEAD.
  git -C "$REPO" worktree add --detach "$WT" "$SHA" || die "worktree add failed"
fi

# Step 4: verify the pin.
ACTUAL="$(git -C "$WT" rev-parse HEAD)" || die "rev-parse in worktree failed"
[[ "$ACTUAL" == "$SHA" ]] || die "worktree HEAD ($ACTUAL) does not match pinned SHA ($SHA)"

# The parent is needed for diffing; it is normally already present.
if ! git -C "$REPO" cat-file -e "$PARENT^{commit}" 2>/dev/null; then
  echo "Parent $PARENT not present locally; attempting fetch ..." >&2
  git -C "$REPO" fetch "$GERRIT_HOST/$GERRIT_PROJECT" "$PARENT" 2>/dev/null \
    || echo "fetch-cl.sh: WARNING: parent commit unavailable — fetch/sync mainline before diffing" >&2
fi

# Write pin.md from the saved JSON.
python3 - "$REVIEW_DIR" "$CL" "$PS" "$CURRENT_PS" "$SHA" "$PARENT" "$REF" "$WT" <<'PYEOF'
import json, os, sys

rd, cl, ps, cur, sha, parent, ref, wt = sys.argv[1:9]

def load(path):
    raw = open(path, 'rb').read()
    if raw.startswith(b")]}'"):
        raw = raw.split(b'\n', 1)[1]
    return json.loads(raw)

d = load(os.path.join(rd, 'detail.json'))
try:
    c = load(os.path.join(rd, 'comments.json'))
except Exception:
    c = {}

unresolved = sum(1 for msgs in c.values() for m in msgs if m.get('unresolved'))
total_comments = sum(len(msgs) for msgs in c.values())
rev = d['revisions'][sha]
files = sorted(f for f in rev.get('files', {}) if not f.startswith('/'))
owner = d.get('owner', {})

lines = [f"# CL {cl} — patchset {ps} pin", ""]
lines.append(f"- Subject: {d.get('subject', '')}")
lines.append(f"- Status: {d.get('status', '')}")
lines.append(f"- Owner: {owner.get('name', '?')} <{owner.get('email', '?')}>")
lines.append(f"- Updated: {d.get('updated', '')}")
lines.append(f"- Current patchset: {cur}")
lines.append(f"- Pinned patchset: {ps}")
lines.append(f"- Revision SHA: {sha}")
lines.append(f"- Parent SHA: {parent}")
lines.append(f"- Ref: {ref}")
lines.append(f"- Worktree: {wt} (rev-parse verified)")
lines.append(f"- Messages: {len(d.get('messages', []))}; comment threads: "
             f"{total_comments} ({unresolved} unresolved)")
if files:
    lines.append(f"- Files changed ({len(files)}):")
    lines.extend(f"  - {f}" for f in files)
else:
    lines.append("- Files changed: not included in this fetch (pinned patchset "
                 "is not current); enumerate with git diff --name-only")

desc = rev.get('commit', {}).get('message', '')
if desc:
    lines += ["", "## CL description (pinned revision)", "", "```",
              desc.rstrip(), "```"]

with open(os.path.join(rd, 'pin.md'), 'w') as f:
    f.write("\n".join(lines) + "\n")

print(f"pin.md written; {unresolved} unresolved comment thread(s)")
PYEOF

cat <<EOF

Pinned CL $CL patchset $PS
  review dir : $REVIEW_DIR
  worktree   : $WT
  revision   : $SHA
  parent     : $PARENT
  diff       : git -C "$WT" diff $PARENT $SHA
EOF

if [[ "$PS" != "$CURRENT_PS" ]]; then
  echo "  NOTE       : pinned patchset $PS is NOT current (current is $CURRENT_PS)"
fi

cat <<EOF
  (re-run this script before final output to detect newer patchsets)

The worktree is read-only for review purposes. Remove it when the review is
done:  git -C "$REPO" worktree remove "$WT"
EOF
