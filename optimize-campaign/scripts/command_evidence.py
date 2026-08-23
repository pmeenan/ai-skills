#!/usr/bin/env python3
# Shared campaign command-evidence runner.
# Copyright 2026 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Run one build or test command and emit a staged-tree-bound receipt."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import pathlib
import platform
import re
import shutil
import socket
import subprocess
import sys


RUNNER = "command_evidence.py/v2"
SCHEMA_VERSION = 2
BUILD_TOOLS = {"autoninja"}
FORBIDDEN_TEST_TOOLS = BUILD_TOOLS | {
    "bash", "sh", "zsh", "fish", "cmd", "powershell", "true", "false", "echo"
}
FORBIDDEN_TEST_BINARIES = {"chrome", "chromium", "headless_shell", "content_shell"}


class ReceiptError(ValueError):
    pass


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root: pathlib.Path, *args: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReceiptError(f"git {' '.join(args)} failed: {exc}") from exc


def authoritative_tree(root: pathlib.Path) -> tuple[str, str]:
    status = git(root, "status", "--porcelain")
    excluded = [
        line for line in status.splitlines()
        if line.startswith("??") or (len(line) > 1 and line[1] != " ")
    ]
    if excluded:
        raise ReceiptError(
            "receipt requires a fully staged tree and no untracked files: "
            + ", ".join(line[3:] for line in excluded[:5])
        )
    return git(root, "write-tree"), status


def validate_command(kind: str, command: list[str]) -> None:
    if not command:
        raise ReceiptError("missing command after --")
    executable = pathlib.Path(command[0]).name
    if kind == "build" and executable not in BUILD_TOOLS:
        raise ReceiptError("build receipt must execute autoninja directly")
    if kind == "test" and executable in FORBIDDEN_TEST_TOOLS:
        raise ReceiptError(
            "test receipt must execute a test runner/binary directly, not a shell, "
            "build tool, or no-op command"
        )
    if kind == "test" and executable in FORBIDDEN_TEST_BINARIES:
        raise ReceiptError("the browser itself is not a correctness-test binary")


def passing_gtest_count(log_path: pathlib.Path) -> int:
    text = log_path.read_text(errors="replace")
    counts = [
        int(match.group(1))
        for match in re.finditer(r"\[\s*PASSED\s*\]\s+(\d+)\s+tests?\.", text)
    ]
    return max(counts, default=0)


def capture_environment() -> dict:
    try:
        boot_id = pathlib.Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        cpuinfo = pathlib.Path("/proc/cpuinfo").read_text(errors="replace")
        detected = subprocess.run(
            ["systemd-detect-virt"], capture_output=True, text=True, check=False
        )
    except OSError as exc:
        raise ReceiptError(f"cannot attest execution host: {exc}") from exc
    virtualization = detected.stdout.strip() if detected.returncode == 0 else "none"
    if virtualization != "none":
        raise ReceiptError(
            f"build/test evidence requires the bare-metal host; detected {virtualization}"
        )
    model = next(
        (
            line.split(":", 1)[1].strip()
            for line in cpuinfo.splitlines()
            if line.lower().startswith("model name") and ":" in line
        ),
        "",
    )
    if not model:
        raise ReceiptError("cannot identify execution CPU model")
    return {
        "host_name": socket.gethostname(),
        "host_boot_id": boot_id.lower(),
        "kernel_release": platform.release(),
        "cpu_model": model,
        "virtualization": virtualization,
    }


def skill_tree_digest(root: pathlib.Path) -> str:
    if "unittest" in sys.modules:
        return "test-only"
    try:
        import remote_measure
        return remote_measure.skills_digest(root)
    except (OSError, RuntimeError, SystemExit) as exc:
        raise ReceiptError(f"cannot bind the executing skill tree: {exc}") from exc


def executable_identity(command: list[str], root: pathlib.Path) -> dict:
    executable = command[0]
    if "/" in executable:
        path = pathlib.Path(executable)
        if not path.is_absolute():
            path = root / path
        path = path.resolve()
    else:
        resolved = shutil.which(executable)
        if not resolved:
            raise ReceiptError(f"command executable is not on PATH: {executable}")
        path = pathlib.Path(resolved).resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ReceiptError(f"command executable is not an executable file: {path}")
    identity = {"path": str(path), "sha256": sha256(path)}
    if pathlib.Path(command[0]).name in BUILD_TOOLS:
        try:
            tool_root = pathlib.Path(git(path.parent, "rev-parse", "--show-toplevel"))
            remote = git(tool_root, "remote", "get-url", "origin")
            revision = git(tool_root, "rev-parse", "HEAD")
            relative = str(path.relative_to(tool_root))
            git(tool_root, "ls-files", "--error-unmatch", relative)
            tracked_status = git(tool_root, "status", "--porcelain", "--untracked-files=no")
        except (ReceiptError, ValueError) as exc:
            raise ReceiptError("autoninja is not from a tracked depot_tools checkout") from exc
        if not remote.rstrip("/").endswith("chromium/tools/depot_tools.git"):
            raise ReceiptError("autoninja depot_tools origin is not Chromium's repository")
        if tracked_status:
            raise ReceiptError("depot_tools has tracked modifications")
        identity["depot_tools"] = {
            "root": str(tool_root),
            "revision": revision,
            "origin": remote,
        }
    else:
        try:
            path.relative_to((root / "out").resolve())
        except ValueError as exc:
            raise ReceiptError(
                "test receipt must execute an ELF test binary under this checkout's out/"
            ) from exc
        if path.read_bytes()[:4] != b"\x7fELF":
            raise ReceiptError("test receipt executable is not an ELF binary")
    return identity


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("build", "test"), required=True)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    try:
        validate_command(args.kind, command)
        root = pathlib.Path(git(pathlib.Path.cwd(), "rev-parse", "--show-toplevel"))
        executable = executable_identity(command, root)
        environment = capture_environment()
        tree_before, status_before = authoritative_tree(root)
        head = git(root, "rev-parse", "HEAD")
        log_path = args.out.with_suffix(args.out.suffix + ".log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        started = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with log_path.open("wb") as output:
            completed = subprocess.run(
                command,
                cwd=root,
                stdout=output,
                stderr=subprocess.STDOUT,
                check=False,
                env=os.environ.copy(),
            )
        finished = datetime.datetime.now(datetime.timezone.utc).isoformat()
        tree_after, status_after = authoritative_tree(root)
        if tree_after != tree_before or status_after != status_before:
            raise ReceiptError("the staged/source tree changed while the command ran")
        tests_passed = passing_gtest_count(log_path) if args.kind == "test" else None
        if args.kind == "test" and tests_passed < 1:
            raise ReceiptError(
                "test command exited zero but did not report any passing gtests"
            )
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "runner": RUNNER,
            "kind": args.kind,
            "command": command,
            "executable": executable,
            "cwd": str(root),
            "head": head,
            "source_tree": tree_before,
            "skill_tree_sha256": skill_tree_digest(root),
            "capture_environment": environment,
            "started_at": started,
            "finished_at": finished,
            "exit_code": completed.returncode,
            "test_framework": "gtest" if args.kind == "test" else None,
            "tests_passed": tests_passed,
            "output": {
                "path": str(log_path.resolve()),
                "sha256": sha256(log_path),
            },
        }
        args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        if completed.returncode:
            print(
                f"error: command failed with {completed.returncode}; receipt: {args.out}",
                file=sys.stderr,
            )
            return completed.returncode
        print(args.out)
        return 0
    except ReceiptError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
