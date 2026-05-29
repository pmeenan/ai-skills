---
name: chrome-profiling
description: Provides instructions and tools to run system-wide simpleperf profiling on Android devices with root access, resolving typical permission and file corruption issues.
---
# Chrome Android Profiling Skill (simpleperf)

When you need to collect and analyze C++ profiles for Chrome on an Android device, follow this systematic, robust process to bypass security and file corruption hurdles.

## 1. Build Configuration
You can profile successfully using a standard developer build with symbols enabled. 
Configure your `args.gn` on the host:
```gn
target_os = "android"
target_cpu = "arm" # or arm64 depending on device
is_debug = false
symbol_level = 1
blink_symbol_level = 1
v8_symbol_level = 1
is_official_build = true
is_component_build = false
```
Build and install the APK as usual:
```bash
autoninja -C out/Android chrome_public_apk
adb install out/Android/apks/ChromePublic.apk
```

## 2. Device Security Relaxation
You must relax kernel and SELinux security settings on the rooted device to allow profiling:
```bash
adb shell su -c "echo -1 > /proc/sys/kernel/perf_event_paranoid"
adb shell su -c "setprop security.perf_harden 0"
adb shell su -c "setenforce 0" # Set SELinux to Permissive
```

## 3. Tool Compatibility (Binary Push)
To avoid format version mismatches between the device and the host:
- Push the compatible `simpleperf` binary from the host NDK to the device:
  ```bash
  adb push third_party/android_toolchain/ndk/simpleperf/bin/android/arm/simpleperf /data/local/tmp/simpleperf_ndk
  # Use android/arm64/simpleperf if the device is 64-bit
  adb shell chmod 777 /data/local/tmp/simpleperf_ndk
  ```

## 4. Crossbench Code Modifications
If running the profile via Crossbench, you must apply two critical modifications to force local execution, root privileges, and clean process termination:

### A. Force Local Imports (`cb.py`)
To ensure `vpython3` doesn't ignore your local code edits in favor of cached/installed packages, modify `third_party/crossbench/cb.py` to prepend the local directory to `sys.path`:
```python
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
```

### B. Robust Root Profiling & SIGINT Termination (`android.py`)
Modify `third_party/crossbench/crossbench/probes/profiling/context/android.py`:
1.  **Use Pushed Binary & Root**: In `generate_simpleperf_command_line`, set the binary to `/data/local/tmp/simpleperf_ndk` and return the command wrapped in `su -c`:
    ```python
    command_line: ListCmdArgs = ["/data/local/tmp/simpleperf_ndk", "record"]
    ...
    import shlex
    return ["su", "-c", shlex.join(str(x) for x in command_line)]
    ```
2.  **Match Binary Name**: In `_get_simpleperf_pids`, change the process name check to use substring matching so it finds `simpleperf_ndk`:
    ```python
    if "simpleperf" in process["name"]:
    ```
3.  **Clean SIGINT Termination (Crucial)**: Do **not** kill the parent `su` process, as that abruptly terminates the profiler and corrupts the file (missing index/footer). Instead, explicitly send `SIGINT` (`kill -2`) directly to `simpleperf_ndk` on the device, then wait for the host wrapper:
    ```python
    def stop_process(self) -> None:
      if self._profiling_process:
        # Explicitly send SIGINT to simpleperf on the device as root
        for pid in self._get_simpleperf_pids():
          logging.info("Sending SIGINT to simpleperf process on device: %d", pid)
          try:
            self.browser_platform.sh("su", "-c", f"kill -2 {pid}")
          except Exception as e:
            logging.error("Failed to kill simpleperf on device: %s", e)
        
        # Wait for the host adb process to exit
        try:
          self._profiling_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
          logging.warning("Host profiling process timed out, forcing kill")
          self._profiling_process.kill()
        self._profiling_process = None
        self.browser.performance_mark("probe-profiling-stop")
    ```

## 5. Host-Side Offline Symbolization
Once Crossbench completes, it automatically pulls `simpleperf.perf.data` to the host (located in the story's run directory). Because the file was terminated cleanly, you can run `report.py` on the host NDK using your build directory for symbol lookup:
```bash
PATH=$PATH:third_party/llvm-build/Release+Asserts/bin \
python3 third_party/android_toolchain/ndk/simpleperf/report.py \
  -i <path_to_pulled_perf.data> \
  --symdir out/Android \
  --children \
  -o <path_to_output_report.txt>
```

This will generate a fully symbolized call graph report with accumulated children overhead on the host.
