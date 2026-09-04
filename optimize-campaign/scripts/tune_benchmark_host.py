#!/usr/bin/env python3
# Copyright 2026 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Manage CPU and kernel tuning for consistent benchmark execution on Linux hosts.

Provides:
  - enable:  Locks CPU governors to performance, disables turbo boost (locks base
             clock), disables ASLR, turns off SMT siblings, and quiets kernel
             interrupts. Saves previous host state to a JSON file so it can be
             cleanly restored.
  - disable: Restores the host state from the saved JSON file (or safe defaults)
             so the machine is not left permanently locked.
  - status:  Reports current tuning parameters.
  - run:     Executes a benchmark command within a tuned context, restoring on exit.

Usage:
  # Enable tuning before a benchmark cycle:
  python3 tune_benchmark_host.py enable

  # Restore host state after benchmark completion:
  python3 tune_benchmark_host.py disable

  # Check current status:
  python3 tune_benchmark_host.py status

  # Run a command inside a tuned session:
  python3 tune_benchmark_host.py run -- vpython3 run_ab_benchmark.py ...
"""

import argparse
import contextlib
import glob
import json
import os
import pathlib
import shutil
import subprocess
import sys

DEFAULT_STATE_FILE = "/tmp/bench_host_tuning_state.json"

SYS_NO_TURBO = "/sys/devices/system/cpu/intel_pstate/no_turbo"
SYS_SMT = "/sys/devices/system/cpu/smt/control"
SYS_GOV_CPU0 = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"
SYS_EPP_CPU0 = "/sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference"
SYS_GOVERNOR_PATTERN = "/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor"
SYS_EPP_PATTERN = "/sys/devices/system/cpu/cpu*/cpufreq/energy_performance_preference"
PROC_ASLR = "/proc/sys/kernel/randomize_va_space"
PROC_NMI = "/proc/sys/kernel/nmi_watchdog"


def is_root():
    return os.geteuid() == 0


def run_priv(cmd, check=True):
    """Run command, prefixing with sudo if not already root."""
    if not is_root():
        cmd = ["sudo", "-n"] + cmd
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def can_tune_host() -> bool:
    """Return True if privileges (root or passwordless sudo) are available to tune the host."""
    if is_root():
        return True
    try:
        res = subprocess.run(["sudo", "-n", "true"], capture_output=True, check=False)
        return res.returncode == 0
    except OSError:
        return False


@contextlib.contextmanager
def tuned_host_context(state_file=DEFAULT_STATE_FILE, disable_smt=True):
    """Context manager to enable host tuning and restore on exit."""
    if not can_tune_host():
        yield False
        return
    try:
        enable_tuning(state_file=state_file, disable_smt=disable_smt)
        yield True
    finally:
        disable_tuning(state_file=state_file)


def write_sys_file(path, value):
    """Write value to a sysfs or procfs path with privileges."""
    path = str(path)
    if not os.path.exists(path):
        return False
    value_str = str(value).strip() + "\n"
    if is_root():
        try:
            with open(path, "w") as f:
                f.write(value_str)
            return True
        except OSError as e:
            print(f"Warning: Failed writing to {path}: {e}", file=sys.stderr)
            return False
    else:
        try:
            subprocess.run(
                ["sudo", "-n", "tee", path],
                input=value_str,
                capture_output=True,
                text=True,
                check=True,
            )
            return True
        except subprocess.SubprocessError as e:
            print(f"Warning: Failed writing to {path} via sudo: {e}", file=sys.stderr)
            return False


def read_sys_file(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            return f.read().strip()
    except OSError:
        return None


def get_current_state():
    """Capture current tuning configuration."""
    return {
        "governor": read_sys_file(SYS_GOV_CPU0),
        "epp": read_sys_file(SYS_EPP_CPU0),
        "no_turbo": read_sys_file(SYS_NO_TURBO),
        "smt": read_sys_file(SYS_SMT),
        "aslr": read_sys_file(PROC_ASLR),
        "nmi_watchdog": read_sys_file(PROC_NMI),
    }


def print_status(state=None):
    if state is None:
        state = get_current_state()

    print("=" * 64)
    print("Benchmark Host Tuning Status:")
    print("-" * 64)

    turbo_str = "Unknown"
    if state.get("no_turbo") == "1":
        turbo_str = "Disabled (Clocks locked to base frequency) [TUNED]"
    elif state.get("no_turbo") == "0":
        turbo_str = "Enabled (Thermal boosting active) [STOCK]"
    print(f"  Intel Turbo Boost:     {turbo_str}")

    gov_str = state.get("governor") or "Unknown"
    if gov_str == "performance":
        gov_str += " [TUNED]"
    elif gov_str == "powersave":
        gov_str += " [STOCK]"
    print(f"  CPU Governor:          {gov_str}")

    epp_str = state.get("epp") or "Unknown"
    if epp_str == "performance":
        epp_str += " [TUNED]"
    elif epp_str == "balance_performance":
        epp_str += " [STOCK]"
    print(f"  Energy Pref (EPP):     {epp_str}")

    aslr_str = state.get("aslr") or "Unknown"
    if aslr_str == "0":
        aslr_str = "0 (Disabled / Deterministic) [TUNED]"
    elif aslr_str == "2":
        aslr_str = "2 (Full randomization) [STOCK]"
    print(f"  ASLR:                  {aslr_str}")

    smt_str = state.get("smt") or "Unknown"
    if smt_str == "off":
        smt_str = "off (Physical cores only) [TUNED]"
    elif smt_str == "on":
        smt_str = "on (Hyperthreads active) [STOCK]"
    print(f"  SMT / Hyperthreading:  {smt_str}")

    nmi_str = state.get("nmi_watchdog") or "Unknown"
    if nmi_str == "0":
        nmi_str = "0 (Disabled) [TUNED]"
    print(f"  NMI Watchdog:          {nmi_str}")
    print("=" * 64)


def set_governor(governor_name):
    """Set CPU frequency governor on all online CPUs."""
    if shutil.which("cpupower"):
        try:
            run_priv(["cpupower", "frequency-set", "-g", governor_name], check=True)
            return True
        except subprocess.SubprocessError:
            pass

    success = False
    for gov_file in sorted(glob.glob(SYS_GOVERNOR_PATTERN)):
        if write_sys_file(gov_file, governor_name):
            success = True
    return success


def set_epp(epp_name):
    """Set energy performance preference on all online CPUs."""
    success = False
    for epp_file in sorted(glob.glob(SYS_EPP_PATTERN)):
        if write_sys_file(epp_file, epp_name):
            success = True
    return success


def enable_tuning(state_file=DEFAULT_STATE_FILE, disable_smt=True):
    """Enable consistent benchmark tuning and save previous state."""
    current = get_current_state()

    # Save pre-tuning state if not already recorded
    if not os.path.exists(state_file):
        try:
            with open(state_file, "w") as f:
                json.dump(current, f, indent=2)
            print(f"Saved pre-tuning host state to {state_file}", file=sys.stderr)
        except OSError as e:
            print(f"Warning: Could not save host state: {e}", file=sys.stderr)

    print("Enabling consistent benchmark host tuning...", file=sys.stderr)

    # 1. Optionally disable SMT (hyperthreading) to isolate physical cores first
    if disable_smt and os.path.exists(SYS_SMT):
        write_sys_file(SYS_SMT, "off")

    # 2. Lock CPU governor to performance
    set_governor("performance")

    # 3. Lock Energy Performance Preference to performance
    set_epp("performance")

    # 4. Disable Intel Turbo Boost (locks frequency flat to base clock)
    if os.path.exists(SYS_NO_TURBO):
        write_sys_file(SYS_NO_TURBO, "1")

    # 5. Disable ASLR for deterministic binary & memory layout
    if os.path.exists(PROC_ASLR):
        write_sys_file(PROC_ASLR, "0")

    # 6. Disable NMI watchdog interrupts
    if os.path.exists(PROC_NMI):
        write_sys_file(PROC_NMI, "0")

    print("Benchmark host tuning ENABLED.", file=sys.stderr)
    print_status()


def disable_tuning(state_file=DEFAULT_STATE_FILE):
    """Restore host state from saved JSON file or safe defaults."""
    saved_state = {}
    if os.path.exists(state_file):
        try:
            with open(state_file, "r") as f:
                saved_state = json.load(f)
            print(f"Restoring host state from {state_file}...", file=sys.stderr)
        except OSError as e:
            print(f"Warning: Could not read {state_file}: {e}", file=sys.stderr)

    # Restore defaults if no saved state
    target_governor = saved_state.get("governor") or "powersave"
    target_epp = saved_state.get("epp") or "balance_performance"
    target_no_turbo = saved_state.get("no_turbo") or "0"
    target_aslr = saved_state.get("aslr") or "2"
    target_nmi = saved_state.get("nmi_watchdog") or "1"
    target_smt = saved_state.get("smt") or "on"

    print("Restoring host power and scheduling configuration...", file=sys.stderr)

    # 1. Restore SMT first so all CPUs come online before governor assignment
    if os.path.exists(SYS_SMT):
        write_sys_file(SYS_SMT, target_smt)

    # 2. Restore governor
    set_governor(target_governor)

    # 3. Restore EPP
    set_epp(target_epp)

    # 4. Restore Turbo Boost
    if os.path.exists(SYS_NO_TURBO):
        write_sys_file(SYS_NO_TURBO, target_no_turbo)

    # 5. Restore ASLR
    if os.path.exists(PROC_ASLR):
        write_sys_file(PROC_ASLR, target_aslr)

    # 6. Restore NMI watchdog
    if os.path.exists(PROC_NMI):
        write_sys_file(PROC_NMI, target_nmi)

    if os.path.exists(state_file):
        try:
            os.remove(state_file)
        except OSError:
            pass

    print("Benchmark host tuning DISABLED. Machine restored to normal.", file=sys.stderr)
    print_status()


def main():
    parser = argparse.ArgumentParser(
        description="Manage CPU and kernel tuning for benchmark host consistency."
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    p_enable = subparsers.add_parser("enable", help="Enable benchmark tuning (locks clocks, ASLR, SMT).")
    p_enable.add_argument("--state-file", default=DEFAULT_STATE_FILE, help="Path to save pre-tuning state.")
    p_enable.add_argument("--keep-smt", action="store_true", help="Keep SMT enabled instead of disabling siblings.")

    p_disable = subparsers.add_parser("disable", help="Disable benchmark tuning and restore original state.")
    p_disable.add_argument("--state-file", default=DEFAULT_STATE_FILE, help="Path to pre-tuning state file.")

    subparsers.add_parser("status", help="Print current tuning status.")

    p_run = subparsers.add_parser("run", help="Run a command within a tuned session, restoring on exit.")
    p_run.add_argument("--state-file", default=DEFAULT_STATE_FILE, help="Path to save state.")
    p_run.add_argument("--keep-smt", action="store_true", help="Keep SMT enabled.")
    p_run.add_argument("cmd", nargs=argparse.REMAINDER, help="Command to execute.")

    args = parser.parse_args()

    if args.subcommand == "enable":
        enable_tuning(state_file=args.state_file, disable_smt=not args.keep_smt)
        return 0
    elif args.subcommand == "disable":
        disable_tuning(state_file=args.state_file)
        return 0
    elif args.subcommand == "status":
        print_status()
        return 0
    elif args.subcommand == "run":
        if not args.cmd:
            sys.exit("Error: no command provided to run.")
        cmd = args.cmd
        if cmd[0] == "--":
            cmd = cmd[1:]
        with tuned_host_context(state_file=args.state_file, disable_smt=not args.keep_smt):
            res = subprocess.run(cmd)
            return res.returncode


if __name__ == "__main__":
    sys.exit(main())
