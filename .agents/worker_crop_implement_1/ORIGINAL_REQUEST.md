## 2026-06-18T16:16:27Z
You are the Cropping Standard Worker.
Your working directory is: C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\worker_crop_implement_1
Your task is to implement the cropping algorithm improvements in `server/id_photo_engine_minimal/crop.py`.

Please follow these guidelines:
1. Replace the crop logic in `server/id_photo_engine_minimal/crop.py` with the proposed dynamic 70% head ratio, hair volume mask detection, horizontal centering, and top/bottom margin controls.
You can use the proposed code written by Explorer 1 at C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\explorer_crop_audit_1\proposed_crop.py as a complete implementation reference.
2. Run the validation and regression tests using:
- `npm run verify:id-photo-quality`
- `npm run verify:full-business-flow`
To verify the cropping logic is correct, passes all quality thresholds, and doesn't break regression tests.
Ensure the test logs are captured and reported in your handoff.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

When completed, write a handoff report at `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\worker_crop_implement_1\handoff.md` and send a message back to the orchestrator.
