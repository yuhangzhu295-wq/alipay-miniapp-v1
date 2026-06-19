# BRIEFING — 2026-06-18T16:15:56Z

## Mission
Explore the cropping algorithm in server/id_photo_engine_minimal/crop.py and identify how to implement dynamic head ratio, hair volume detection, top/bottom gaps, horizontal centering, and adaptive cropping.

## 🔒 My Identity
- Archetype: Teamwork explorer
- Roles: Read-only investigator, analyzer
- Working directory: C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\explorer_crop_audit_1
- Original parent: 60536f0a-1efa-4397-ac6f-d28b2e35154b
- Milestone: Crop algorithm audit

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- CODE_ONLY network mode - no external web access

## Current Parent
- Conversation ID: 60536f0a-1efa-4397-ac6f-d28b2e35154b
- Updated: 2026-06-18T16:15:56Z

## Investigation State
- **Explored paths**:
  - `server/id_photo_engine_minimal/crop.py` (cropping logic)
  - `server/id_photo_engine_minimal/api.py` (entry points)
  - `server/services/face_detector.py` (face detection landmarks/box format)
  - `server/id_photo_engine_minimal/alpha_cleanup.py` (alpha mask cleaning)
- **Key findings**:
  - Identified how to dynamically adapt head ratio between 65% and 75% while keeping a 10% top gap.
  - Formulated an elegant alpha mask hair top detection combined with landmark estimates and safety limits.
  - Determined mathematical shoulder/clavicle visibility check using landmark head height.
- **Unexplored areas**: None, the mission's scope is fully covered.

## Key Decisions Made
- Scanned existing implementation, identified shortcomings, and designed a mathematical model for dynamic cropping.
- Provided a full code replacement file (`proposed_crop.py`) to streamline work for the implementer agent.

## Artifact Index
- C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\explorer_crop_audit_1\handoff.md — Final handoff report containing findings, math, and logic.
- C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\explorer_crop_audit_1\proposed_crop.py — Proposed crop.py implementation.
