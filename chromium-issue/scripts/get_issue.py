#!/usr/bin/env python3
"""Fetch details of a public Chromium issue from issues.chromium.org.

Usage:
    get_issue.py <issue-number-or-url> [--json]

issues.chromium.org (Google's Buganizer) has no public REST API, but its web
frontend loads each issue from an endpoint that serves *public* issues with no
authentication:

    GET https://issues.chromium.org/action/issues/<id>

The body is XSSI-guarded (a leading ")]}'") and encoded in Buganizer's
positional nested-array format -- fields are identified by index, not name.
This script strips the guard, locates the issue array, decodes the fields, and
prints a readable summary (or JSON with --json).

The field indices and enum tables below were reverse-engineered from real
responses and from the issues.chromium.org JS bundle. They are undocumented and
could change; the script fails loudly rather than emitting wrong data.
"""
import argparse
import datetime
import json
import re
import sys
import urllib.error
import urllib.request

ENDPOINT = "https://issues.chromium.org/action/issues/{}"
ISSUE_URL = "https://issues.chromium.org/issues/{}"

# Enum orders copied verbatim from the issues.chromium.org JS bundle. Responses
# encode these as 1-based integers (0 == *_UNSPECIFIED), so value N -> table[N-1].
STATUS = ("NEW ASSIGNED ACCEPTED FIXED VERIFIED NOT_REPRODUCIBLE "
          "INTENDED_BEHAVIOR OBSOLETE INFEASIBLE DUPLICATE INACTIVE").split()
PRIORITY = ["P0", "P1", "P2", "P3", "P4"]
SEVERITY = ["S0", "S1", "S2", "S3", "S4"]
TYPE = ("BUG FEATURE_REQUEST CUSTOMER_ISSUE INTERNAL_CLEANUP PROCESS "
        "VULNERABILITY PRIVACY_ISSUE PROGRAM PROJECT FEATURE MILESTONE "
        "EPIC STORY TASK").split()


def extract_id(text):
    """Pull the issue number out of a bare ID or any URL containing one."""
    match = re.search(r"\d{6,}", text)
    if not match:
        sys.exit(f"error: no issue number found in {text!r}")
    return match.group(0)


def fetch(issue_id):
    request = urllib.request.Request(
        ENDPOINT.format(issue_id),
        headers={"User-Agent": "Mozilla/5.0 (chromium-issue skill)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        # The endpoint returns a JSON body even for 4xx -- 403 for a restricted
        # issue, 404 for a missing one -- so decode it and let parse() surface
        # the server's message instead of a bare status code.
        raw = err.read().decode("utf-8", "replace")
        if not raw.strip():
            sys.exit(f"error: HTTP {err.code} fetching issue {issue_id}")
    except urllib.error.URLError as err:
        sys.exit(f"error: network failure fetching issue {issue_id}: {err.reason}")
    if raw.startswith(")]}'"):  # XSSI guard; json.loads tolerates the rest
        raw = raw[4:]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(f"error: unexpected (non-JSON) response for issue {issue_id}")


def dig(obj, *path):
    """Walk a chain of list indices, returning None if any step is missing."""
    for key in path:
        if isinstance(obj, list) and isinstance(key, int) and -len(obj) <= key < len(obj):
            obj = obj[key]
        else:
            return None
    return obj


def decode_enum(table, value):
    if isinstance(value, int) and 1 <= value <= len(table):
        return table[value - 1]
    if not value:
        return "UNSPECIFIED"
    return f"UNKNOWN({value})"


def to_datetime(pair):
    """A timestamp is encoded as [seconds, nanos]."""
    seconds = dig(pair, 0)
    if not isinstance(seconds, (int, float)):
        return None
    return datetime.datetime.fromtimestamp(seconds, datetime.timezone.utc)


def person(node):
    """A person is [null, "ab...@host.com", ...]; emails come back redacted."""
    return dig(node, 1)


def component_path(state):
    """The leaf component, e.g. "Internals>Network>Cache"."""
    node = dig(state, 14, 0)
    if isinstance(node, list):
        path = dig(node, 9)  # index 9 holds the plain ">"-joined path
        if isinstance(path, str):
            return path
        strings = [x for x in node if isinstance(x, str)]
        if strings:
            return max(strings, key=len)
    return None


def find_issue(data, issue_id):
    """The success payload is [["b.IssueFetchResponse", [ ...slots... ]]].

    The issue lives in one of those slots as a list whose [1] is the issue id;
    search for it by id rather than hard-coding the slot index.
    """
    container = dig(data, 0, 1)
    if not isinstance(container, list):
        return None
    target = int(issue_id)
    for element in container:
        if isinstance(element, list) and len(element) > 1 and element[1] == target:
            return element
    return None


def parse(data, issue_id):
    if isinstance(data, dict):  # errors arrive as {"message": "..."}
        message = data.get("message", "unknown error")
        if "permission" in message.lower():
            sys.exit(f"Issue {issue_id} is not public (access-restricted). "
                     "Many security and internal issues cannot be viewed "
                     "without a signed-in, authorized account.")
        if message.startswith("Issue ") or str(issue_id) in message:
            sys.exit(message)  # server message already names the issue
        sys.exit(f"Issue {issue_id}: {message}")

    if dig(data, 0, 0) == "er":  # frontend error envelope
        sys.exit(f"error: issue tracker returned an error response "
                 f"(code {dig(data, 0, 5)}) for issue {issue_id}")

    issue = find_issue(data, issue_id)
    if issue is None:
        sys.exit(f"error: could not locate issue {issue_id} in the response "
                 "(the endpoint format may have changed -- the field map in "
                 "get_issue.py needs re-checking against a fresh response).")

    state = dig(issue, 2) or []
    description = dig(issue, 43) or []

    links = []
    for entry in dig(issue, 40) or []:
        url = dig(entry, 0, 0)
        if isinstance(url, str) and url not in links:
            links.append(url)

    return {
        "id": dig(issue, 1),
        "url": ISSUE_URL.format(dig(issue, 1)),
        "title": (dig(state, 5) or "").strip(),
        "type": decode_enum(TYPE, dig(state, 1)),
        "status": decode_enum(STATUS, dig(state, 2)),
        "priority": decode_enum(PRIORITY, dig(state, 3)),
        "severity": decode_enum(SEVERITY, dig(state, 4)),
        "component": component_path(state),
        "reporter": person(dig(state, 6)),
        "assignee": person(dig(state, 7)),
        "ccs": [person(c) for c in (dig(state, 9) or []) if person(c)],
        "created": to_datetime(dig(issue, 4)),
        "modified": to_datetime(dig(issue, 5)),
        "comment_count": dig(issue, 11),
        "links": links,
        "description": dig(description, 0),
        "description_author": person(dig(description, 2)),
        "description_time": to_datetime(dig(description, 3)),
    }


def fmt_dt(value):
    return value.strftime("%Y-%m-%d %H:%M UTC") if value else "-"


def render(info):
    bar = "=" * 72
    out = [
        bar,
        f"Issue {info['id']}: {info['title']}",
        info["url"],
        bar,
        f"Status     {info['status']:<24} Type       {info['type']}",
        f"Priority   {info['priority']:<24} Severity   {info['severity']}",
        f"Component  {info['component'] or '-'}",
        f"Reporter   {info['reporter'] or '-'}",
        f"Assignee   {info['assignee'] or '-'}",
    ]
    if info["ccs"]:
        out.append(f"CC         {', '.join(info['ccs'])}")
    out.append(f"Created    {fmt_dt(info['created'])}")
    out.append(f"Modified   {fmt_dt(info['modified'])}")
    if info["comment_count"] is not None:
        out.append(f"Comments   {info['comment_count']} "
                   f"(full thread in browser: {info['url']})")
    if info["links"]:
        out.append("")
        out.append(f"Related links ({len(info['links'])}):")
        out.extend(f"  - {url}" for url in info["links"])
    out.append("")
    out.append("-" * 72)
    when = info["description_time"]
    out.append(f"Description (by {info['description_author'] or '?'}, "
               f"{when.strftime('%Y-%m-%d') if when else '?'}):")
    out.append("-" * 72)
    out.append(info["description"] or "(no description)")
    out.append(bar)
    return "\n".join(out)


def to_json(info):
    serializable = dict(info)
    for key in ("created", "modified", "description_time"):
        serializable[key] = info[key].isoformat() if info[key] else None
    return json.dumps(serializable, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(
        description="Fetch details of a public Chromium issue.")
    parser.add_argument("issue", help="issue number or issues.chromium.org URL")
    parser.add_argument("--json", action="store_true",
                        help="emit structured JSON instead of a text summary")
    args = parser.parse_args()

    issue_id = extract_id(args.issue)
    info = parse(fetch(issue_id), issue_id)
    print(to_json(info) if args.json else render(info))


if __name__ == "__main__":
    main()
