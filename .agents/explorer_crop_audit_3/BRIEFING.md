# BRIEFING — 2026-06-19T00:16:00+08:00

## Mission
Analyze the cropping algorithm in `server/id_photo_engine_minimal/crop.py` and identify how to implement dynamic head ratio, hair volume detection, top gap/shoulders constraints, horizontal centering, and spec-adaptiveness.

## 🔒 My Identity
- Archetype: Cropping Algorithm Explorer 3
- Roles: Investigator, Analyzer
- Working directory: C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\explorer_crop_audit_3
- Original parent: 60536f0a-1efa-4397-ac6f-d28b2e35154b
- Milestone: Crop Algorithm Audit

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- Analyze server/id_photo_engine_minimal/crop.py
- Do not run code edits
- Provide math and logic in handoff.md

## Current Parent
- Conversation ID: 8a1eb24c-2e2f-4bcd-b35a-1afe7eda1650
- Updated: 2026-06-19T00:16:00+08:00

## Investigation State
- **Explored paths**: `server/id_photo_engine_minimal/crop.py`, `server/services/face_detector.py`, `server/services/id_photo_specs.py`
- **Key findings**: Formulated mathematical model combining landmarks and alpha channel foreground mask for true head top detection and dynamic shoulder adjustment.
- **Unexplored areas**: Implementation and real-world testing (read-only constraint).

## Key Decisions Made
- Established coordinate system, search boundaries, and multi-variable optimization algorithm to dynamically balance $R \in [0.65, 0.75]$ and $g \in [0.08, 0.12]$ while keeping shoulders visible.

## Artifact Index
- C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\explorer_crop_audit_3\handoff.md — Handoff report containing findings and recommendations
