#!/usr/bin/env python3
"""Run campaign commands on the test machine that owns the campaign state.

The campaign directory (`ledger.json`, dossiers, reviews, measurements) lives
on the measurement host under `<remote_src>/.agents/campaigns/<name>`. An
agent working elsewhere keeps coding and analysis local, but every
`campaign.py` command is executed on that host so there is exactly one ledger.

A local pointer file (`.agents/campaigns/current.remote`) records the host,
the remote checkout and the campaign name. When it exists (or `--host` is
given), `campaign.py` forwards itself:

- local file arguments are uploaded into `<campaign>/inbox/<digest>/` and the
  argument is rewritten to the uploaded path;
- a local `remote_measure.py` summary that carries `host_summary_path` is
  replaced by that host path, so measurement evidence is never re-uploaded;
- `--out` / `--summary-out` targets are written on the host under
  `<campaign>/outbox/` and fetched back to the requested local path;
- the remote skill tree must match the local digest (same gate as
  `remote_measure.py`), so both sides run identical enforcement code.

Running on the test machine itself (pointer host == this host) never
forwards; the local ledger is the store.
"""
import hashlib
import json
import os
import pathlib
import shlex
import socket
import subprocess
import sys

POINTER_NAME = "current.remote"
DOWNLOAD_FLAGS = ("--out", "--summary-out")
# First contact with a new host is accepted; a changed key is still refused.
SSH_OPTS = ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new"]
LOCAL_HOST_ALIASES = ("localhost", "127.0.0.1", "::1")


class HostError(RuntimeError):
    pass


def pointer_path(root):
    return pathlib.Path(root) / ".agents" / "campaigns" / POINTER_NAME


def load_pointer(root):
    path = pointer_path(root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise HostError(f"unreadable campaign pointer {path}: {exc}") from exc
    for field in ("host", "remote_src", "name"):
        if not isinstance(data.get(field), str) or not data[field]:
            raise HostError(f"campaign pointer {path} lacks {field}")
    return data


def save_pointer(root, host, remote_src, name):
    path = pointer_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"host": host, "remote_src": remote_src, "name": name}, indent=2) + "\n")
    return path


def is_local_host(host):
    if not host:
        return True
    names = {socket.gethostname(), socket.gethostname().split(".")[0], *LOCAL_HOST_ALIASES}
    try:
        names.add(socket.getfqdn())
    except OSError:
        pass
    target = host.split("@", 1)[-1]
    return target in names or target.split(".")[0] in {n.split(".")[0] for n in names}


def remote_campaign_dir(remote_src, name):
    return f"{remote_src.rstrip('/')}/.agents/campaigns/{name}"


def _file_digest(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _host_summary_path(path):
    """A local remote_measure summary whose evidence already lives on the host."""
    try:
        data = json.loads(pathlib.Path(path).read_text())
    except (OSError, ValueError):
        return None
    value = data.get("host_summary_path") if isinstance(data, dict) else None
    return value if isinstance(value, str) and value.startswith("/") else None


def plan_forward(argv, remote_dir, is_file=None):
    """Rewrite argv for the host; return (remote_argv, uploads, downloads).

    `uploads` are (local, remote) file pairs; `downloads` are (remote, local)
    pairs fetched after the command. Only argument *values* are inspected;
    flag names and the subcommand are passed through.
    """
    is_file = is_file or (lambda p: pathlib.Path(p).is_file())
    remote_argv = []
    uploads = []
    downloads = []
    pending_flag = None
    for index, token in enumerate(argv):
        if index == 0 or (token.startswith("-") and pending_flag is None and "=" not in token):
            if token == "--dir":
                pending_flag = "--dir"
                continue
            if token in DOWNLOAD_FLAGS:
                pending_flag = token
                remote_argv.append(token)
                continue
            if token.startswith("--"):
                pending_flag = token
            remote_argv.append(token)
            continue
        flag = None
        value = token
        if token.startswith("--") and "=" in token and pending_flag is None:
            flag, value = token.split("=", 1)
        elif pending_flag is not None:
            flag = pending_flag
        pending_flag = None
        if flag == "--dir":
            continue
        rewritten = value
        if flag in DOWNLOAD_FLAGS:
            local = pathlib.Path(value)
            rewritten = f"{remote_dir}/outbox/{local.name}"
            downloads.append((rewritten, str(local)))
        elif value and not value.startswith("-") and is_file(value):
            host_path = _host_summary_path(value)
            if host_path:
                rewritten = host_path
            else:
                digest = _file_digest(value)[:12]
                rewritten = f"{remote_dir}/inbox/{digest}/{pathlib.Path(value).name}"
                uploads.append((value, rewritten))
        if flag and token.startswith("--") and "=" in token:
            remote_argv.append(f"{flag}={rewritten}")
        else:
            remote_argv.append(rewritten)
    return remote_argv, uploads, downloads


def _ssh(host, script, stdin_data=None):
    proc = subprocess.run(
        ["ssh", *SSH_OPTS, host, "bash", "-s"],
        input=(script if stdin_data is None else script).encode(),
        capture_output=True,
    )
    return proc.returncode, proc.stdout.decode(errors="replace"), proc.stderr.decode(errors="replace")


def forward(host, remote_src, name, argv, expected_digest=None):
    """Upload inputs, run campaign.py on the host, fetch outputs; return rc."""
    from remote_measure import sync_gate_lines
    remote_dir = remote_campaign_dir(remote_src, name)
    remote_argv, uploads, downloads = plan_forward(argv, remote_dir)
    q = shlex.quote
    if uploads:
        dirs = sorted({str(pathlib.PurePosixPath(remote).parent) for _, remote in uploads})
        rc, _, err = _ssh(host, "mkdir -p " + " ".join(q(d) for d in dirs) + "\n")
        if rc:
            raise HostError(f"cannot create inbox on {host}: {err.strip()}")
        for local, remote in uploads:
            subprocess.run(["scp", *SSH_OPTS, "-C", "-q", local, f"{host}:{remote}"], check=True)
    if downloads:
        dirs = sorted({str(pathlib.PurePosixPath(remote).parent) for remote, _ in downloads})
        rc, _, err = _ssh(host, "mkdir -p " + " ".join(q(d) for d in dirs) + "\n")
        if rc:
            raise HostError(f"cannot create outbox on {host}: {err.strip()}")
    lines = ["set -euo pipefail", f"cd {q(remote_src)}"]
    if expected_digest:
        lines += sync_gate_lines(expected_digest)
    # init creates <campaigns>/<name> itself and repoints the host's `current`
    # link, which host-side tools (remote_measure in local mode) rely on.
    dir_option = "" if remote_argv and remote_argv[0] == "init" else f"--dir {q(remote_dir)} "
    lines.append(
        "python3 .agents/skills/optimize-campaign/scripts/campaign.py "
        + dir_option + " ".join(q(a) for a in remote_argv)
    )
    script = "\n".join(lines) + "\n"
    print(f"+ ssh {host} campaign.py {dir_option}{' '.join(remote_argv)}", file=sys.stderr)
    proc = subprocess.Popen(["ssh", *SSH_OPTS, host, "bash", "-s"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    proc.stdin.write(script.encode())
    proc.stdin.close()
    for raw in proc.stdout:
        sys.stdout.write(raw.decode(errors="replace"))
    proc.wait()
    if proc.returncode == 0 and downloads:
        for remote, local in downloads:
            pathlib.Path(local).parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["rsync", "-az", "-e", "ssh " + " ".join(SSH_OPTS), f"{host}:{remote}", local], check=True)
    return proc.returncode


def strip_host_args(argv):
    """Remove --host/--remote-src from argv; return (argv, host, remote_src)."""
    out = []
    host = None
    remote_src = None
    skip = None
    for token in argv:
        if skip is not None:
            if skip == "--host":
                host = token
            else:
                remote_src = token
            skip = None
            continue
        if token in ("--host", "--remote-src"):
            skip = token
            continue
        if token.startswith("--host="):
            host = token.split("=", 1)[1]
            continue
        if token.startswith("--remote-src="):
            remote_src = token.split("=", 1)[1]
            continue
        out.append(token)
    return out, host, remote_src


def rewrite_paths(value, local_prefix, remote_prefix):
    """Recursively map local_prefix -> remote_prefix in every string."""
    if isinstance(value, str):
        if value == local_prefix or value.startswith(local_prefix.rstrip("/") + "/"):
            return remote_prefix + value[len(local_prefix.rstrip("/")):]
        return value
    if isinstance(value, list):
        return [rewrite_paths(v, local_prefix, remote_prefix) for v in value]
    if isinstance(value, dict):
        return {k: rewrite_paths(v, local_prefix, remote_prefix) for k, v in value.items()}
    return value


def write_host_file(host, remote_path, text):
    q = shlex.quote
    script = f"mkdir -p {q(str(pathlib.PurePosixPath(remote_path).parent))} && cat > {q(remote_path)}\n"
    proc = subprocess.run(["ssh", *SSH_OPTS, host, "bash", "-c", script],
                          input=text.encode(), capture_output=True)
    if proc.returncode:
        raise HostError(f"cannot write {remote_path} on {host}: {proc.stderr.decode(errors='replace').strip()}")
    return remote_path


def read_host_json(host, remote_path):
    proc = subprocess.run(["ssh", *SSH_OPTS, host, "cat", shlex.quote(remote_path)],
                          capture_output=True)
    if proc.returncode:
        raise HostError(f"cannot read {remote_path} on {host}: {proc.stderr.decode(errors='replace').strip()}")
    return json.loads(proc.stdout.decode())
