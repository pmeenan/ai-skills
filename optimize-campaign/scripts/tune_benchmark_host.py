#!/usr/bin/env python3
"""Verified Linux benchmark tuning with exact per-policy restoration.

Requested settings must be supported and read back correctly. This controls
frequency bounds, not a promise that silicon never thermally throttles.

Session-scoped controls (all restored on exit, in reverse order):

- CPU: no turbo, performance governor/EPP, min=max=base frequency, NMI
  watchdog off, optionally SMT off.
- ASLR: disabled only when the caller asks (cycle-probe captures). Score A/B
  runs keep ASLR on so per-repetition layout randomization averages out
  alignment luck instead of freezing one layout per arm.
- Console VT: switched to the benchmark X server's VT so the GPU renders for
  it (NVIDIA renders only for the X server owning the active VT); the previous
  VT is restored afterwards.
- GPU clocks: optionally locked to a fixed graphics clock with nvidia-smi and
  reset afterwards.
"""
import argparse
import contextlib
import glob
import json
import os
import pathlib
import signal
import subprocess
import sys

from measurement_host import lease, observe, active_vt

DEFAULT_STATE_FILE='/tmp/bench_host_tuning_state.json'
SYS_NO_TURBO='/sys/devices/system/cpu/intel_pstate/no_turbo'
SYS_SMT='/sys/devices/system/cpu/smt/control'
PROC_ASLR='/proc/sys/kernel/randomize_va_space'
PROC_NMI='/proc/sys/kernel/nmi_watchdog'


def read_sys_file(path):
    try: return pathlib.Path(path).read_text().strip()
    except OSError: return None


def is_root(): return os.geteuid()==0


def run_priv(cmd,check=True):
    return subprocess.run(([] if is_root() else ['sudo','-n'])+cmd,
                          capture_output=True,text=True,check=check)


def can_tune_host():
    if is_root(): return True
    try: return run_priv(['true'],check=False).returncode==0
    except OSError: return False


def write_sys_file(path,value):
    wanted=str(value).strip()
    if is_root(): pathlib.Path(path).write_text(wanted+'\n')
    else:
        subprocess.run(['sudo','-n','tee',str(path)],input=wanted+'\n',
                       text=True,capture_output=True,check=True)
    actual=read_sys_file(path)
    if actual!=wanted:
        raise RuntimeError(f'tuning readback failed: {path}: wanted {wanted!r}, observed {actual!r}')
    return True


def get_current_state():
    paths=[SYS_NO_TURBO,SYS_SMT,PROC_ASLR,PROC_NMI]
    for policy in sorted(glob.glob('/sys/devices/system/cpu/cpufreq/policy*')):
        paths.extend(str(pathlib.Path(policy)/name) for name in
                     ('scaling_governor','energy_performance_preference','scaling_min_freq','scaling_max_freq'))
    return {p:value for p in paths if (value:=read_sys_file(p)) is not None}


def switch_vt(vt):
    """Switch the console to `vt` and verify the kernel agrees."""
    wanted=f'tty{int(vt)}'
    if active_vt()==wanted: return wanted
    result=run_priv(['chvt',str(int(vt))],check=False)
    if result.returncode:
        raise RuntimeError(f'chvt {vt} failed: {result.stderr.strip() or result.returncode}')
    for _ in range(50):
        if active_vt()==wanted: return wanted
        __import__('time').sleep(0.1)
    raise RuntimeError(f'console VT did not switch to {wanted} (active: {active_vt()})')


def lock_gpu_clocks(mhz):
    mhz=int(mhz)
    if mhz<=0: raise RuntimeError('GPU clock lock requires a positive MHz value')
    result=run_priv(['nvidia-smi','--lock-gpu-clocks',f'{mhz},{mhz}'],check=False)
    if result.returncode:
        raise RuntimeError(f'nvidia-smi --lock-gpu-clocks failed: {result.stderr.strip() or result.stdout.strip()}')
    return mhz


def reset_gpu_clocks():
    result=run_priv(['nvidia-smi','--reset-gpu-clocks'],check=False)
    if result.returncode:
        raise RuntimeError(f'nvidia-smi --reset-gpu-clocks failed: {result.stderr.strip() or result.stdout.strip()}')


def _restore(saved):
    # Bring siblings online before restoring each policy; expand frequency
    # limits before narrowing them so min/max writes never cross illegally.
    if SYS_SMT in saved: write_sys_file(SYS_SMT,saved[SYS_SMT])
    if SYS_NO_TURBO in saved: write_sys_file(SYS_NO_TURBO,saved[SYS_NO_TURBO])
    for p in sorted(saved):
        if p.endswith('/scaling_max_freq'):
            current=int(read_sys_file(p) or 0)
            if int(saved[p])>current: write_sys_file(p,saved[p])
    for p in sorted(saved):
        if p.endswith('/scaling_min_freq'): write_sys_file(p,saved[p])
    # intel_pstate rejects an energy_performance_preference write while the
    # governor is still `performance`, so the governor must go back first.
    for p in sorted(saved):
        if p.endswith('/scaling_governor'): write_sys_file(p,saved[p])
    for p in sorted(saved):
        if p not in (SYS_SMT,SYS_NO_TURBO) and not p.endswith(('/scaling_min_freq','/scaling_governor')):
            write_sys_file(p,saved[p])


def service_is_active(name):
    result=subprocess.run(['systemctl','is-active','--quiet',name],capture_output=True,text=True,check=False)
    return result.returncode==0


def pause_services(names):
    """Stop the named systemd services for the session; return those that were running."""
    paused=[]
    for name in names or []:
        if not service_is_active(name): continue
        result=run_priv(['systemctl','stop',name],check=False)
        if result.returncode:
            raise RuntimeError(f'systemctl stop {name} failed: {result.stderr.strip() or result.returncode}')
        paused.append(name)
    return paused


def resume_services(names):
    problems=[]
    for name in names or []:
        result=run_priv(['systemctl','start',name],check=False)
        if result.returncode: problems.append(f'systemctl start {name} failed: {result.stderr.strip() or result.returncode}')
    if problems: raise RuntimeError('; '.join(problems))


def _restore_extras(extras):
    """Undo VT, GPU and service controls; every failure is reported, none is skipped."""
    problems=[]
    if extras.get('paused_services'):
        try: resume_services(extras['paused_services'])
        except RuntimeError as exc: problems.append(str(exc))
    if extras.get('gpu_clock_lock_mhz'):
        try: reset_gpu_clocks()
        except RuntimeError as exc: problems.append(str(exc))
    previous=extras.get('previous_vt')
    if previous:
        try:
            match=__import__('re').fullmatch(r'tty(\d+)',previous)
            if not match: raise RuntimeError(f'unparseable saved VT {previous!r}')
            switch_vt(int(match.group(1)))
        except RuntimeError as exc: problems.append(str(exc))
    if problems: raise RuntimeError('; '.join(problems))


def enable_tuning(state_file=DEFAULT_STATE_FILE,disable_smt=True,disable_aslr=True,vt=None,gpu_clock_mhz=None,pause=None):
    if not can_tune_host(): raise RuntimeError('requested tuning requires root or passwordless sudo')
    saved=get_current_state()
    if SYS_NO_TURBO not in saved: raise RuntimeError('no supported Intel frequency policy; use an explicitly calibrated untuned configuration')
    policies=sorted({str(pathlib.Path(p).parent) for p in saved if p.endswith('/scaling_governor')})
    if not policies: raise RuntimeError('no CPU frequency policies available')
    bases={p:read_sys_file(p+'/base_frequency') for p in policies}
    if any(not v or int(v)<=0 for v in bases.values()): raise RuntimeError('cannot determine base frequency for every policy')
    extras={'previous_vt':active_vt() if vt is not None else None,'gpu_clock_lock_mhz':None,'paused_services':[],
            'requested':{'disable_smt':disable_smt,'disable_aslr':disable_aslr,'vt':vt,'gpu_clock_mhz':gpu_clock_mhz,
                         'pause_services':list(pause or [])}}
    path=pathlib.Path(state_file)
    # Never overwrite a previous session's recovery record.
    with path.open('x') as out: json.dump({'owner_pid':os.getpid(),'saved':saved,'extras':extras},out)
    try:
        write_sys_file(SYS_NO_TURBO,'1')
        for p in policies:
            write_sys_file(p+'/scaling_governor','performance')
            if p+'/energy_performance_preference' in saved:
                write_sys_file(p+'/energy_performance_preference','performance')
            if int(saved[p+'/scaling_min_freq']) > int(bases[p]):
                write_sys_file(p+'/scaling_min_freq',bases[p])
            write_sys_file(p+'/scaling_max_freq',bases[p])
            write_sys_file(p+'/scaling_min_freq',bases[p])
        if disable_aslr: write_sys_file(PROC_ASLR,'0')
        write_sys_file(PROC_NMI,'0')
        if disable_smt and SYS_SMT in saved: write_sys_file(SYS_SMT,'off')
        if vt is not None:
            switch_vt(vt)
        if gpu_clock_mhz:
            extras['gpu_clock_lock_mhz']=lock_gpu_clocks(gpu_clock_mhz)
            path.write_text(json.dumps({'owner_pid':os.getpid(),'saved':saved,'extras':extras}))
        if pause:
            # Other GPU tenants (an LLM server, for example) must not share the
            # card mid-run; stop them for the session and restart afterwards.
            extras['paused_services']=pause_services(pause)
            path.write_text(json.dumps({'owner_pid':os.getpid(),'saved':saved,'extras':extras}))
        return {'requested':'controlled','extras':extras,'before':saved,'during':get_current_state(),'observations':observe()}
    except BaseException:
        try: _restore_extras(extras)
        finally:
            _restore(saved)
            path.unlink()
        raise


def disable_tuning(state_file=DEFAULT_STATE_FILE):
    path=pathlib.Path(state_file)
    state=json.loads(path.read_text())
    if not isinstance(state.get('saved'),dict) or not state['saved']:
        raise RuntimeError('missing valid saved state; refusing guessed restore defaults')
    extras=state.get('extras') or {}
    _restore(state['saved'])
    restored=get_current_state()
    if any(restored.get(p)!=v for p,v in state['saved'].items()):
        raise RuntimeError('restoration incomplete; recovery record retained')
    _restore_extras(extras)
    path.unlink()
    return restored


@contextlib.contextmanager
def tuned_host_context(state_file=DEFAULT_STATE_FILE,disable_smt=True,disable_aslr=True,vt=None,gpu_clock_mhz=None,pause=None):
    with lease():
        report=enable_tuning(state_file,disable_smt,disable_aslr,vt,gpu_clock_mhz,pause)
        handlers={}
        def stop(signum,frame): raise SystemExit(128+signum)
        if __import__('threading').current_thread() is __import__('threading').main_thread():
            for signum in (signal.SIGTERM,signal.SIGINT):
                handlers[signum]=signal.signal(signum,stop)
        try: yield report
        finally:
            try: report['restored']=disable_tuning(state_file)
            finally:
                for signum,handler in handlers.items(): signal.signal(signum,handler)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    subs=parser.add_subparsers(dest='action',required=True)
    for action in ('enable','disable','status','run'):
        sub=subs.add_parser(action)
        sub.add_argument('--state-file',default=DEFAULT_STATE_FILE)
        sub.add_argument('--keep-smt',action='store_true')
        sub.add_argument('--keep-aslr',action='store_true',
                         help='leave ASLR enabled (score runs); cycle-probe captures disable it')
        sub.add_argument('--vt',type=int,default=None,
                         help='console VT owned by the benchmark X server (switched to for the session, restored after)')
        sub.add_argument('--gpu-clock-mhz',type=int,default=None,
                         help='lock the NVIDIA graphics clock at this MHz for the session')
        sub.add_argument('--pause-service',action='append',default=[],
                         help='systemd service to stop for the session and restart afterwards (repeatable), e.g. ollama')
        sub.add_argument('--report')
        if action=='run': sub.add_argument('command',nargs=argparse.REMAINDER)
    args=parser.parse_args()
    if args.action=='status': print(json.dumps({'sysfs':get_current_state(),'active_vt':active_vt()},indent=2)); return 0
    if args.action=='enable': result=enable_tuning(args.state_file,not args.keep_smt,not args.keep_aslr,args.vt,args.gpu_clock_mhz,args.pause_service)
    elif args.action=='disable': result=disable_tuning(args.state_file)
    else:
        command=args.command[1:] if args.command[:1]==['--'] else args.command
        if not command: parser.error('run needs a command after --')
        with tuned_host_context(args.state_file,not args.keep_smt,not args.keep_aslr,args.vt,args.gpu_clock_mhz,args.pause_service) as result:
            rc=subprocess.run(command).returncode
        if args.report: pathlib.Path(args.report).write_text(json.dumps(result,indent=2)+'\n')
        return rc
    print(json.dumps(result,indent=2)); return 0


if __name__=='__main__':
    try: sys.exit(main())
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as exc:
        sys.exit(str(exc))
