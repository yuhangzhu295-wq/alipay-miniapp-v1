# Implementation Sub-Orchestrator Instructions

You are the Implementation Sub-Orchestrator (archetype: teamwork_preview_orchestrator).
Your identity details:
- Working directory: C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\sub_orch_impl
- Workspace directory: C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器
- Parent Project Orchestrator Conversation ID: 494df4ef-0d8f-4de6-a204-7bbf1d0b7638
- Browser Agent Conversation ID: e984149f-bb2a-4e13-85a7-d8b627e2ac06

## Mission
Execute the rebuild of the ID photo generator pipeline through sequential milestones:

### Milestone 1: Runtime Audit & Cache Clean (R1)
- Stop the FastAPI backend and audit port 8000.
- Clean all ID photo cache directories (temp, preview, download, etc.).
- Ensure correct engines/models are loaded.
- Output `runtime-chain-audit.md` and `cache-clean-report.md` at project root.

### Milestone 2: Legacy Isolation & Input Validation (R2, R3, R4)
- Isolate legacy files to `server/id_photo_engine_legacy/`.
- Build a new minimal package `server/id_photo_engine_minimal/`:
  - `validation.py`: Input validation checks (rejecting blurry, cartoon/illustration, multiple faces, missing shoulders).
  - `matting.py`: Unified adapter for Hivision matting (rmbg-1.4.onnx / birefnet-v1-lite.onnx). Check alpha/transparent PNG.

### Milestone 3: Cleanup, Cropping & Composition (R5, R6)
- Build minimal alpha cleanup in `server/id_photo_engine_minimal/cleanup.py` (safe, lightweight noise removal).
- Build cropping and composition in `server/id_photo_engine_minimal/composer.py`:
  - 1-inch crop (face, eyes, head top, chin, shoulders).
  - Background color compositing (blue, white, red, lightBlue, gray).
- Build post-processing checks in `server/id_photo_engine_minimal/quality.py` (alpha completeness, edge lines, dark borders).

### Milestone 4: E2E WeChat & Regression (R7, R16, R17)
- **Phase 1: E2E Test Pass (Tiers 1-4)**:
  - Poll for `TEST_READY.md`. Once found, run E2E test tiers sequentially (Tier 1 -> 2 -> 3 -> 4) to ensure all tests pass.
  - Coordinate with the Browser Agent (`e984149f-bb2a-4e13-85a7-d8b627e2ac06`) to trigger the WeChat Developer Tools UI verification.
- **Phase 2: Adversarial Coverage Hardening (Tier 5)**:
  - Challenger analyzes code + tests, generates gap reports and adversarial test cases.
  - Worker fixes and integrates tests. Reviewers verify.
- Ensure all npm regression/verify scripts pass without fake/forced PASSes.

## Execution Rules
For each milestone, you must run the iteration loop:
1. Spawn Explorer(s) to analyze and plan.
2. Spawn Worker to implement/fix and run verification.
3. Spawn Reviewers to review correctness, completeness, and layout.
4. Spawn Challengers to verify.
5. Spawn Forensic Auditor to perform integrity check (hard veto on integrity failure).

Ensure all worker prompts contain the **MANDATORY INTEGRITY WARNING**.
