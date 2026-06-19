# BRIEFING — 2026-06-19T00:50:03+08:00

## Mission
Review the correctness, completeness, and safety of the cropping implementation in `server/id_photo_engine_minimal/crop.py`.

## 🔒 My Identity
- Archetype: reviewer_critic
- Roles: reviewer, critic
- Working directory: C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\reviewer_crop_2
- Original parent: 60536f0a-1efa-4397-ac6f-d28b2e35154b
- Milestone: Review Crop Implementation
- Instance: 1 of 1

## 🔒 Key Constraints
- Review-only — do NOT modify implementation code

## Current Parent
- Conversation ID: 60536f0a-1efa-4397-ac6f-d28b2e35154b
- Updated: not yet

## Review Scope
- **Files to review**: server/id_photo_engine_minimal/crop.py
- **Interface contracts**: server/id_photo_engine_minimal/crop.py requirements (70% head ratio, hair volume mask, margins, horizontal centering, adaptive sizing, landmarks fallback)
- **Review criteria**: correctness, style, safety, robustness, conformance

## Key Decisions Made
- Executed local unit tests on `crop_id_photo` directly covering eye-landmarks, faceBox-fallback, alpha-channel fallback, and empty images.
- Verified that all constraints (ratio [0.65, 0.75], 10% top margin, shoulder space, centering, adaptive size) are perfectly implemented.
- Issued an APPROVE verdict.

## Review Checklist
- **Items reviewed**: server/id_photo_engine_minimal/crop.py
- **Verdict**: APPROVE
- **Unverified claims**: none

## Attack Surface
- **Hypotheses tested**: Checked aspect ratio calculation, head top scanning with alpha mask, dynamic ratio clipping, out-of-bounds crop safety, empty image fallback.
- **Vulnerabilities found**: none
- **Untested angles**: none

## Artifact Index
- C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\reviewer_crop_2\handoff.md — Review Handoff Report
