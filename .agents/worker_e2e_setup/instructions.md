# Instructions for worker_e2e_setup

You are teamwork_preview_worker.
Your working directory: C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\worker_e2e_setup\
Your identity: worker_e2e_setup

## Task
1. Run a quick check (e.g. `verify_environment.py`) to see if the server on port 8000 is running.
2. If the server is not running, start it by running `start-hd-watermark-service.bat` in the background (or run `python -m uvicorn main:app --host 0.0.0.0 --port 8000` from the `server` directory).
3. If dependencies are missing, install them.
4. Run `node server/scripts/run_python.js server/scripts/verify_all.py` or run `npm run verify:all` (or individual test commands) and verify which tests pass/fail.
5. Create `TEST_INFRA.md` at the project root outlining the test philosophy, feature inventory, runner setup, and test cases mapped to the 4-tier methodology.
6. Create `TEST_READY.md` at the project root as specified.
7. Return a summary of your run, which tests passed/failed, and confirmation that `TEST_INFRA.md` and `TEST_READY.md` are created.

## ⚠️ MANDATORY INTEGRITY WARNING
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.
