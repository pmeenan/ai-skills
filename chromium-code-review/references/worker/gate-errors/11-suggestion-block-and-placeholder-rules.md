<!-- Generated from ../../gate-errors.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Gate-error lookup table

**Rule this file enforces: never read or grep a helper script's source to work
out what a gate rejection meant.** Look the message up here. If the message you
hit is missing, adding it to this file is part of the fix — the next run must
not have to re-read the script either.

**Do not read this file end to end — query it.** At over 700 rows it is a
database, and reading it would simply relocate the cost it exists to remove:

```sh
<skill-dir>/scripts/explain-gate-error.py "<the message you saw>"
```

Paste the message verbatim, including paths and line numbers; the lookup
ignores them and matches the parameterized form below. Exit 1 means no row
matched, and adding one is then part of the fix.

By hand, if you must: take the distinctive substring of the failure (usually
the part after `ERROR: ` or `<script>.py: ERROR: `), find it in the table for
the script that produced it, and apply the **Fix** verbatim. The trailing **Source** column
names the file and line so a maintainer can re-verify a row; you do not need to
open it to act on the row.

`validate-review-dir.py` prints every finding as `ERROR: <message>` or
`WARNING: <message>` and ends with `FAIL: <n> error(s), <m> warning(s)` or
`PASS: 0 errors, <m> warning(s)`. Warnings never fail the gate. Every other
script prints `<script-name>: ERROR: <message>` on stderr and exits 1.

---

## 11. Suggestion-block and placeholder rules

These two families cause repeated confusing rejections because the error text
does not name the real cause. The rules below are read from the parsers, not
from the messages.

### Fenced-block parsing (`fenced_field`, `fenced_blocks`)

The parser accepts an opening fence with **0 to 3 leading spaces**, and then
requires the closing fence to have **exactly the same indentation**. A block
whose closing ``` is indented differently is never closed, so it is not counted
at all — which is why you get a *count* error rather than an indentation error.

| Symptom | Real cause | Fix | Source |
| --- | --- | --- | --- |
| `applicable Suggested edit has 0 suggestion blocks; expected exactly one` | The opening fence is ` ```suggestion ` but the closing fence is at a different indent (commonly nested under a list item, so the opener is indented 2 spaces and the closer is at column 0, or vice versa). | Put the opening and closing fences at the **same** column, with at most 3 leading spaces. Do not nest the block deeper than 3 spaces under a list item. | validate-review-dir.py:4205, :328 |
| `applicable Suggested edit requires exactly one suggestion block in both draft and Gerrit fragments (found 0 and 1)` | Same indentation mismatch, in one of the two fragments only. | Make the two fragments byte-identical, including fence indentation. | validate-review-dir.py:4570 |
| `applicable Suggested edit lacks a replacement block` / `lacks selected lines` | The fence exists but its info string is wrong (e.g. ```` ```cpp ```` instead of ```` ```suggestion ````), or the ```` - <label>: ```` line has trailing text after the colon. | Use the exact info string the template specifies, and leave the `- <label>:` line empty after the colon; only blank lines may separate it from the fence. | validate-review-dir.py:414, :409, :292 |
| `has malformed applicable Suggested edit target` | The target line does not match `replaces <path>:<start>[-<end>]` with 1-based positive line numbers. | Write `replaces components/foo/bar.cc:120-124`. No leading `./`, no absolute path, no `L` prefix. | validate-review-dir.py:4200, :47 |
| `has a non-specific Suggested edit omission reason` | The omission reason is exactly one of `n/a`, `none`, `not applicable`, `no suggestion`, `omitted` (case-insensitive). | Give a concrete reason, e.g. `omitted — the fix requires changing the Mojo interface, which is out of this CL's scope`. | validate-review-dir.py:4241, :51 |
| Decision line not recognized at all | The field must be `- **Suggested edit:** applicable — ...` (draft/output coverage) or `- Suggested edit decision: applicable — ...` (synthesis card), at the **start of a line**, with either an em dash `—` or an ASCII hyphen `-` as the separator. | Copy the field verbatim from the template; do not indent it and do not change the bolding. | validate-review-dir.py:39, :43 |

### `<...>` placeholder detection in `gerrit-comments.md`

`validate_final` rejects `gerrit-comments.md` if it matches
`(?:file://|/(?:tmp|home)/|<[^>]+>)`.

| Symptom | Real cause | Fix | Source |
| --- | --- | --- | --- |
| `gerrit-comments.md contains a local path/URL or placeholder inline` on a file with no placeholders | The `<[^>]+>` branch matches **any** angle-bracket text, including legitimate C++ that you quoted inline: `std::vector<int>`, `#include <memory>`, `base::OnceCallback<void()>`, or an HTML tag in prose. | Do not put angle-bracket code in **inline** prose. Move it into a fenced code block, or rewrite it without brackets (`a vector of int`, `the memory header`). Quoting with backticks is **not** enough — the regex runs over the whole file text. | validate-review-dir.py:4893 |
| Same message, genuine cause | The file really does contain `file://`, `/tmp/`, `/home/`, or a `<placeholder>`. | Remove the local path or fill in the placeholder. Gerrit comments must be self-contained and must not reference your review directory. | validate-review-dir.py:4893 |

---
