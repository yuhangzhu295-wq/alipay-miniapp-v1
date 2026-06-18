# BRIEFING — 2026-06-17T17:44:24Z

## Mission
Investigate legacy isolation, input validation, and matting adapter design for Milestone 2.

## 🔒 My Identity
- Archetype: Explorer 3
- Roles: Read-only investigator for Milestone 2 (Legacy Isolation & Input Validation)
- Working directory: C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\explorer_m2_3
- Original parent: fff23b23-106a-4eef-a650-02f67d2f700d
- Milestone: Milestone 2: Legacy Isolation & Input Validation (R2, R3, R4)

## 🔒 Key Constraints
- Read-only investigation — do NOT implement or modify any code.
- Analyze legacy isolation (move to `server/id_photo_engine_legacy/`).
- Plan `validation.py` (exact 1 face, blur Laplacian, cartoon check, shoulder detection).
- Plan `matting.py` (Hivision matting with rmbg-1.4.onnx/birefnet-v1-lite.onnx, handle transparent PNGs).

## Current Parent
- Conversation ID: fff23b23-106a-4eef-a650-02f67d2f700d
- Updated: yes (2026-06-17T17:44:24Z)

## Investigation State
- **Explored paths**:
  - `server/` (root and main API server)
  - `server/services/` (legacy file locations)
  - `third_party/HivisionIDPhotos/` (matting model weights and pipeline)
  - `server/scripts/` (test suite)
- **Key findings**:
  - Legacy files are identified as: `id_photo_v2.py`, `portrait_matting.py`, `id_photo_composer.py`, and `id_photo_quality.py`.
  - ONNX weights (`rmbg-1.4.onnx` and `birefnet-v1-lite.onnx`) are confirmed to exist under `third_party/HivisionIDPhotos/hivision/creator/weights/`.
  - Validation metrics (blur score `< 18`, shoulder margins) are extracted.
- **Unexplored areas**: None.

## Key Decisions Made
- Plan to move legacy files to `server/id_photo_engine_legacy/` and update internal/external imports.
- Reuse alpha channel directly when an input image mode is `RGBA` and has transparent pixels.
- Use OpenCV Haar cascades as a robust fallback for face detection inside `validation.py`.

## Artifact Index
- C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\explorer_m2_3\analysis.md — Main Analysis Report
- C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\explorer_m2_3\handoff.md — Handoff Report
