# BRIEFING — 2026-06-19T00:16:15+08:00

## Mission
Explore `server/id_photo_engine_minimal/crop.py` and identify how to implement dynamic head ratio, hair volume detection using alpha mask, top gap & shoulders visibility, horizontal centering, and spec-adaptive cropping without hardcoded limits.

## 🔒 My Identity
- Archetype: Explorer
- Roles: investigator, analyzer, synthesizer
- Working directory: C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\explorer_crop_audit_2
- Original parent: 60536f0a-1efa-4397-ac6f-d28b2e35154b
- Milestone: Crop algorithm analysis

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- Run no code edits, just read and explore

## Current Parent
- Conversation ID: 60536f0a-1efa-4397-ac6f-d28b2e35154b
- Updated: 2026-06-19T00:16:15+08:00

## Investigation State
- **Explored paths**:
  - `server/id_photo_engine_minimal/crop.py` (cropping algorithm)
  - `server/id_photo_engine_minimal/api.py` (API calling context)
  - `server/services/face_detector.py` (face detection structure)
  - `server/services/portrait_quality.py` (portrait quality and shoulder detection metrics)
  - `server/services/id_photo_specs.py` (target specifications)
- **Key findings**:
  - Formulated a new relative mathematical cropping algorithm that scans the alpha channel centered on the face to detect hair volume and correct head height.
  - Set up dynamic head ratios [65%, 75%] targeting 70% with a shoulder-visibility constraint.
  - Aligned crop boundaries to keep a 10% top gap.
  - Centered horizontally using the calculated face center.
- **Unexplored areas**:
  - Direct implementation (read-only constraint).

## Key Decisions Made
- Formulated the exact equations for crown mask clamping, true head height adjustment, minimum height constraint for shoulder visibility, and dynamic head ratio calculations.
- Put proposed replacement code in `handoff.md`.

## Artifact Index
- C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\explorer_crop_audit_2\handoff.md — Analysis and recommendation report
