#!/usr/bin/env python3
"""Shared measurement lease, display/GPU identity and read-only host observations.

Every runner (score A/B, cycle profile, mechanism capture) must render through
the same surface. `display_environment` describes that surface and fails closed
when the requested X display is missing or does not own the console VT, because
on the NVIDIA driver only the X server on the active VT actually renders.
"""
import contextlib
import fcntl
import glob
import os
import pathlib
import re
import subprocess
import tempfile
import time

LOCK_FILE = '/tmp/chromium-benchmark-measure.lock'
X11_SOCKET_DIR = '/tmp/.X11-unix'
ACTIVE_VT_PATH = '/sys/class/tty/tty0/active'
DEFAULT_VIEWPORT = '1500x1000'
SOFTWARE_RENDERERS = ('swiftshader', 'llvmpipe', 'softpipe', 'subzero')
CHROME_PROCESS_NAMES = ('chrome', 'chromium', 'content_shell', 'headless_shell')


@contextlib.contextmanager
def lease(path=LOCK_FILE):
    """Use the wrapper's inherited flock when present; otherwise acquire it.

    A duplicate of an inherited open file description shares its flock. Never
    explicitly unlock that descriptor: the parent still owns the session.
    """
    inherited=None
    try:
        identity=os.stat(path)
        for item in pathlib.Path('/proc/self/fd').iterdir():
            try:
                fd=int(item.name)
                stat=os.fstat(fd)
                if fd>2 and (stat.st_dev,stat.st_ino)==(identity.st_dev,identity.st_ino):
                    inherited=os.dup(fd)
                    break
            except (OSError,ValueError): pass
    except FileNotFoundError: pass
    fd=inherited if inherited is not None else os.open(path,os.O_CREAT|os.O_RDWR,0o600)
    try:
        try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc: raise RuntimeError('another measurement holds the host lease') from exc
        yield
    finally:
        os.close(fd)


def read(path):
    try: return pathlib.Path(path).read_text().strip()
    except OSError: return None


def active_vt():
    """Console VT name such as `tty2`, or None when the kernel does not expose it."""
    return read(ACTIVE_VT_PATH)


def _nvidia_query(args, timeout=15):
    try:
        result=subprocess.run(['nvidia-smi',*args],capture_output=True,text=True,timeout=timeout,check=False)
    except (OSError,subprocess.SubprocessError):
        return None
    if result.returncode: return None
    return [[cell.strip() for cell in line.split(',')] for line in result.stdout.splitlines() if line.strip()]


def _int_or_none(value):
    try: return int(value)
    except (TypeError,ValueError): return None


def gpu_observation():
    """Read-only NVIDIA snapshot: clocks, utilization, temperature and compute apps.

    Returns None when no NVIDIA tooling exists. Foreign compute apps (anything
    that is not Chrome) are recorded so a run can prove the GPU was not shared.
    """
    gpus=_nvidia_query(['--query-gpu=index,utilization.gpu,clocks.gr,clocks.mem,temperature.gpu,clocks_throttle_reasons.active','--format=csv,noheader,nounits'])
    if gpus is None: return None
    apps=_nvidia_query(['--query-compute-apps=pid,process_name,used_memory','--format=csv,noheader,nounits']) or []
    compute_apps=[]
    for row in apps:
        if len(row)<3: continue
        name=row[1]
        compute_apps.append({'pid':_int_or_none(row[0]),'process_name':name,'used_memory_mib':_int_or_none(row[2]),
                             'foreign':pathlib.PurePath(name).name not in CHROME_PROCESS_NAMES})
    return {'gpus':[{'index':_int_or_none(r[0]),'utilization_pct':_int_or_none(r[1]),'graphics_clock_mhz':_int_or_none(r[2]),
                     'memory_clock_mhz':_int_or_none(r[3]),'temperature_c':_int_or_none(r[4]),
                     'throttle_reasons':r[5] if len(r)>5 else None} for r in gpus if len(r)>=5],
            'compute_apps':compute_apps}


def observe():
    patterns=(
        '/sys/devices/system/cpu/cpufreq/policy*/scaling_cur_freq',
        '/sys/devices/system/cpu/cpu*/thermal_throttle/*throttle_count',
        '/sys/class/thermal/thermal_zone*/temp',
        '/sys/class/drm/card*/device/gpu_busy_percent',
        '/sys/class/drm/card*/gt_cur_freq_mhz',
    )
    return {'monotonic_ns':time.monotonic_ns(),'loadavg':read('/proc/loadavg'),
            'cpu_pressure':read('/proc/pressure/cpu'),'io_pressure':read('/proc/pressure/io'),
            'online_cpus':read('/sys/devices/system/cpu/online'),
            'cpu_affinity':sorted(os.sched_getaffinity(0)),
            'active_vt':active_vt(),
            'gpu':gpu_observation(),
            'counters':{p:read(p) for pattern in patterns for p in sorted(glob.glob(pattern))}}


def parse_display(display):
    match=re.fullmatch(r':(\d+)(?:\.\d+)?',display or '')
    if not match: raise ValueError(f'display must look like :1, got {display!r}')
    return int(match.group(1))


def display_environment(display=None, expected_vt=None, viewport=None):
    """Describe the rendering surface every runner must share.

    `display=None` means Chrome's headless mode (software rendering). An X
    display must exist and, when `expected_vt` is given, own the console so the
    GPU actually renders for it. Both cases are recorded in the manifest as
    part of the calibration identity.
    """
    vt=active_vt()
    if not display:
        return {'mode':'headless','display':None,'viewport':'headless','expected_vt':None,'active_vt':vt}
    number=parse_display(display)
    socket=pathlib.Path(X11_SOCKET_DIR)/f'X{number}'
    if not socket.exists():
        raise RuntimeError(f'X display {display} is not running (no {socket}); start the benchmark X server first')
    if expected_vt is not None:
        wanted=f'tty{int(expected_vt)}'
        if vt!=wanted:
            raise RuntimeError(f'X display {display} needs the console VT {wanted} but {vt} is active; '
                               'run the measurement inside the tuner session (or `chvt`) first')
    return {'mode':'x11','display':display,'viewport':viewport or DEFAULT_VIEWPORT,
            'expected_vt':int(expected_vt) if expected_vt is not None else None,'active_vt':vt}


def crossbench_display_args(environment):
    """Crossbench flags selecting the surface described by `display_environment`."""
    if environment['mode']=='headless': return ['--headless']
    return [f"--viewport={environment['viewport']}"]


def subprocess_env(environment, base=None):
    env=dict(os.environ if base is None else base)
    if environment['mode']=='x11':
        env['DISPLAY']=environment['display']
        env.pop('WAYLAND_DISPLAY',None)
    else:
        env.pop('DISPLAY',None)
    return env


RENDERER_PROBE_URL=('data:text/html,<script>try{var g=document.createElement("canvas").getContext("webgl");'
                    'var d=g&&g.getExtension("WEBGL_debug_renderer_info");'
                    'console.log("BENCHMARK_GPU_RENDERER: "+(g?(d?g.getParameter(d.UNMASKED_RENDERER_WEBGL):g.getParameter(g.RENDERER)):"NO-WEBGL"))}'
                    'catch(e){console.log("BENCHMARK_GPU_RENDERER: ERROR "+e)}</script>')


def probe_gpu_renderer(browser, environment, timeout=45):
    """Launch the browser once on the requested surface and read its GPU renderer string."""
    with tempfile.TemporaryDirectory(prefix='gpu-probe-') as profile:
        command=[str(browser),'--no-sandbox',f'--user-data-dir={profile}','--no-first-run','--no-default-browser-check',
                 '--disable-background-networking','--enable-logging=stderr','--v=0']
        if environment['mode']=='headless': command.append('--headless')
        command.append(RENDERER_PROBE_URL)
        proc=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
                              env=subprocess_env(environment))
        renderer=None; deadline=time.monotonic()+timeout
        try:
            os.set_blocking(proc.stderr.fileno(),False)
            buffer=b''
            while time.monotonic()<deadline and renderer is None:
                try: chunk=proc.stderr.read()
                except BlockingIOError: chunk=None
                if chunk: buffer+=chunk
                elif proc.poll() is not None: break
                else: time.sleep(0.1)
                match=re.search(rb'BENCHMARK_GPU_RENDERER: ([^"\n]*)',buffer)
                if match: renderer=match.group(1).decode('utf-8','replace').strip()
        finally:
            if proc.poll() is None:
                proc.terminate()
                try: proc.wait(timeout=10)
                except subprocess.TimeoutExpired: proc.kill()
    if not renderer: raise RuntimeError(f'could not read the GPU renderer from {browser} on {environment["mode"]} surface')
    return renderer


def is_software_renderer(renderer):
    return any(token in (renderer or '').lower() for token in SOFTWARE_RENDERERS)


def attest_renderer(environment, browser):
    """Record the renderer string and refuse software rendering on an X display."""
    renderer=probe_gpu_renderer(browser,environment)
    environment=dict(environment,gpu_renderer=renderer)
    if environment['mode']=='x11' and is_software_renderer(renderer):
        raise RuntimeError(f'display {environment["display"]} rendered with {renderer!r}; the GPU is not driving this display')
    return environment


def display_identity(environment):
    """Fields that must match across calibration and measurement sessions."""
    if not isinstance(environment,dict): return None
    return {k:environment.get(k) for k in ('mode','display','viewport','gpu_renderer')}


def foreign_gpu_apps(rows):
    """Names of non-Chrome GPU compute processes seen in any block observation."""
    seen={}
    for row in rows or []:
        for phase in ('before','after'):
            gpu=(row.get(phase) or {}).get('gpu') or {}
            for app in gpu.get('compute_apps',[]):
                if app.get('foreign'): seen[app.get('pid')]=app.get('process_name')
    return sorted(set(filter(None,seen.values())))


def validate_observations(rows, blocks):
    """Reject incomplete telemetry, topology changes, VT changes and observed throttling.

    Frequency and pressure samples are retained for drift diagnosis; a single
    requested-frequency snapshot is not an effective-frequency measurement.
    """
    if not isinstance(rows,list) or len(rows) != blocks:
        raise ValueError('missing per-block host observations')
    for i,row in enumerate(rows,1):
        if row.get('block') != i or not row.get('before') or not row.get('after'):
            raise ValueError('incomplete host observation block')
        a,b=row['before'],row['after']
        if not a['monotonic_ns'] < b['monotonic_ns']:
            raise ValueError('host observation timestamps are not ordered')
        for key in ('online_cpus','cpu_affinity','active_vt'):
            if a.get(key) != b.get(key): raise ValueError(f'host {key} changed during measurement')
        for path,value in a.get('counters',{}).items():
            if 'throttle_count' in path:
                after=b.get('counters',{}).get(path)
                if value is None or after is None or int(after) != int(value):
                    raise ValueError('thermal throttle counter changed during measurement')
        before_apps={app.get('pid') for app in ((a.get('gpu') or {}).get('compute_apps') or []) if app.get('foreign')}
        after_apps={app.get('pid') for app in ((b.get('gpu') or {}).get('compute_apps') or []) if app.get('foreign')}
        if before_apps != after_apps:
            raise ValueError('a foreign GPU compute process started or stopped during a block')
