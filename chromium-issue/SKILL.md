---
name: chromium-issue
description: >-
  Retrieve the details of a public Chromium issue from issues.chromium.org
  (Google's Buganizer) given an issue number or URL. Use this whenever the user
  mentions a Chromium issue or bug by number, pastes an issues.chromium.org or
  crbug.com link, or asks to look up, summarize, or check the status of a
  Chromium bug — even if they don't explicitly ask for a "lookup". Fetches
  title, status, priority, severity, component, people, dates, linked CLs, and
  the full description without needing any authentication.
---

# Chromium issue lookup

The Chromium issue tracker at `issues.chromium.org` (a public Buganizer
instance) has **no public REST API** — the official Google Issue Tracker API is
gated to Googlers and partners. But the tracker's own web frontend loads each
issue from an endpoint that serves **public issues with no authentication**:

```
GET https://issues.chromium.org/action/issues/<id>
```

`scripts/get_issue.py` wraps that endpoint. It accepts an issue number or any
URL containing one, fetches the issue, decodes the response, and prints a
readable summary.

## Usage

```
python3 scripts/get_issue.py <issue-number-or-url>
python3 scripts/get_issue.py <issue-number-or-url> --json
```

These are all equivalent:

```
python3 scripts/get_issue.py 511602101
python3 scripts/get_issue.py https://issues.chromium.org/issues/511602101
python3 scripts/get_issue.py crbug.com/511602101
```

Run it with the script's path relative to this skill directory, or pass an
absolute path. It needs only Python 3 (standard library) and outbound network
access — no API key, no `pip install`.

Use the default text output when reporting to the user. Pass `--json` only when
you need to extract a specific field programmatically.

## What it returns

- Metadata: title, status, priority, severity, type, component
- People: reporter, assignee, CC list (emails come back partially redacted for
  unauthenticated callers — that is the server's behavior, not a script bug)
- Created / modified timestamps
- Related links: design docs, Gerrit CLs, dashboards
- The **full issue description**

## Limitations — read before using

- **Only individual public issues are reachable.** Access-restricted issues
  return a clear "not public" message. Many security and internal issues are
  restricted; that is expected — relay it plainly to the user, don't treat it
  as a failure.
- **No search.** The list/search endpoint requires a signed-in session, so you
  cannot query by component, keyword, label, or status — you can only fetch an
  issue whose ID you already have. If the user wants a search, tell them it
  isn't possible through this skill and point them at the tracker UI.
- **The follow-up comment thread is not retrieved** — only the description (the
  issue's first comment). The script reports the comment count; for the full
  discussion the user must open the issue URL. In practice the description plus
  the linked CLs carry most of the substance, but if the user specifically
  needs later comments, say so rather than implying the description is the whole
  conversation.
- The endpoint is **undocumented**. If the response format changes, the script
  exits with a "format may have changed" message instead of printing wrong
  data — see below.

## Maintenance notes

The endpoint returns Buganizer's positional nested-array JSON behind a leading
`)]}'` XSSI guard. `get_issue.py` strips the guard, finds the issue array by ID,
and reads fields by index. Status/priority/severity/type arrive as 1-based
integers; the enum name tables in the script were copied from the
issues.chromium.org JS bundle.

If a fetch starts failing with "could not locate issue ... the endpoint format
may have changed", the positional field map needs re-checking: fetch a known
public issue (e.g. `curl -s https://issues.chromium.org/action/issues/511602101`),
strip the `)]}'` prefix, and re-map the indices in `get_issue.py` against the
fresh structure.
