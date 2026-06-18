# Milestone 1 Review Report

This report evaluates the correctness, completeness, layout compliance, and formatting of the Milestone 1 outputs:
1. `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\runtime-chain-audit.md`
2. `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\cache-clean-report.md`

---

# Part 1: Quality Review

## Review Summary

**Verdict**: **APPROVE**

The audit and cleanup reports are correct, complete, properly structured, and format-compliant. They accurately document the state of the processes, startup scripts, cache locations, and model weights.

## Findings

### [Minor] Finding 1: Dynamic Re-occupation of Port 8000 and Cache Generation
- **What**: Port 8000 is reported as "Stopped", and cache folders are reported as cleared (0.00 MB). However, running verification scripts immediately restarts the backend service (currently PID `3932`) and recreates cache files (e.g. in `Temp\idphoto_hivision_ascii\runtime` and `Temp\id_photo_server\outputs`).
- **Where**: `runtime-chain-audit.md` (Section 1) and `cache-clean-report.md` (Section 1).
- **Why**: This is not a defect in the cleanup task itself; it is the natural consequence of executing testing/verification scripts after the cleanup. However, readers should be aware that the "Stopped" status and "0.00 MB" cache sizes represent the state *immediately following the execution of the cleanup*, and are dynamically recreated upon backend reuse.
- **Suggestion**: Add a note explaining that testing/runtime reuse will restart the uvicorn backend and regenerate cache files.

## Verified Claims

- **Claim**: Port 8000 process (PID `39008`) was stopped.
  - *Verified via*: `netstat -ano | findstr 8000` and process start time lookup.
  - *Result*: **PASS**. Port 8000 is no longer occupied by PID `39008`. (Though it is now occupied by PID `3932` which was started at `0:31:04` by the verification process).
- **Claim**: Port 8081 IOPaint process is active under PID `46208`.
  - *Verified via*: `powershell (Get-CimInstance Win32_Process -Filter "ProcessId = 46208").CommandLine`
  - *Result*: **PASS**. The process running on port 8081 is indeed `iopaint` with PID `46208`.
- **Claim**: Model weights are present and intact in their designated paths.
  - *Verified via*: Running PowerShell `Get-ChildItem` on the weights directories.
  - *Result*: **PASS**. All 7 model weights exist with correct byte sizes (e.g. `birefnet-v1-lite.onnx` is `224005088` bytes, `big-lama.pt` is `205669692` bytes).
- **Claim**: Startup batch scripts exist and perform described functions.
  - *Verified via*: Reading `start-hd-watermark-service.bat` and `start-watermark-service.bat`.
  - *Result*: **PASS**. Their configuration and reload behavior match the audit description.

## Coverage Gaps

- **Log Truncation in Server Folder** — risk level: **Low** — recommendation: **accept risk**
  - While the `logs` folder at the root was successfully cleared, uvicorn error/out logs in `server/` (e.g. `server/uvicorn.err.log`) were not listed in the initial cleanup target. This is acceptable as the primary target was root logs and temp cache.

## Unverified Items

- None. All major claims regarding process IDs, command lines, model files, and cache paths were fully verified on the host system.

---

# Part 2: Adversarial Review / Challenge Report

## Challenge Summary

**Overall risk assessment**: **LOW**

The cleanup strategy is robust, preserves core model weights, and uses native PowerShell commands to safely stop processes and delete files without violating the prohibited command rules (no `taskkill`, `del /s`, `rmdir /s` was executed).

## Challenges

### [Low] Challenge 1: Process Leak on Reloading Server
- **Assumption challenged**: Terminating the master uvicorn PID will release all related processes.
- **Attack scenario**: When uvicorn is started with `--reload`, it spawns a master supervisor process and one or more child worker processes. If a script forces termination on only the master PID, the child worker process could theoretically be orphaned and continue holding the socket or consuming memory.
- **Blast radius**: Port collision on restart, or phantom background memory usage.
- **Mitigation**: When stopping the backend, verify that both the supervisor and its child processes are terminated, or stop them by querying processes matching the command line pattern.

### [Low] Challenge 2: Temporary File Buildup in AppData/Local/Temp
- **Assumption challenged**: The cleanup script removes all intermediate files.
- **Attack scenario**: The matting service creates files via `NamedTemporaryFile(delete=False)`. These are placed in the root of the system Temp directory rather than in the project-specific cache folders.
- **Blast radius**: Local disk space accumulation over time.
- **Mitigation**: The report correctly identifies this root cause in Section 2. We recommend implementing an automated cron job or incorporating temp png file cleaning of patterns like `tmp*.png` into the server's lifecycle or deployment scripts.

## Stress Test Results

- **Shutdown under lock**: Stop-Process terminates uvicorn PID under forced condition -> expected to exit instantly -> actual behavior: exits immediately, port released -> **PASS**.
- **Model weights deletion attempt**: Cleanup script executed -> expected to ignore model weights folders -> actual behavior: weights remain intact -> **PASS**.

## Unchallenged Areas

- **WeChat Developer Tools integration**: The startup batch scripts attempt to open the WeChat Developer Tools CLI (`cli.bat`). This integration was not stress-tested because the developer tools GUI/CLI environment is local to the user session and not critical to the core backend API correctness.
