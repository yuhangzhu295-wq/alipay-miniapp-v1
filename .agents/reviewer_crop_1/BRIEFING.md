# BRIEFING — 2026-06-19T01:10:00+08:00

## Mission
Review the cropping implementation in server/id_photo_engine_minimal/crop.py for correctness, completeness, and safety.

## 🔒 My Identity
- Archetype: reviewer_critic
- Roles: reviewer, critic
- Working directory: C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\reviewer_crop_1
- Original parent: 60536f0a-1efa-4397-ac6f-d28b2e35154b
- Milestone: Review Cropping Implementation
- Instance: 1 of 1

## 🔒 Key Constraints
- Review-only — do NOT modify implementation code.
- Focus on: Dynamic 70% head ratio, hair volume mask, margins (top 10%, bottom shoulder/clavicle), horizontal centering, adaptive sizing.
- Check missing landmarks fallback, edge conditions, robustness.

## Current Parent
- Conversation ID: 60536f0a-1efa-4397-ac6f-d28b2e35154b
- Updated: 2026-06-19T01:10:00+08:00

## Review Scope
- **Files to review**: `server/id_photo_engine_minimal/crop.py`
- **Interface contracts**: `PROJECT.md` / `SCOPE.md` / requirements in dispatch
- **Review criteria**: correctness, style, safety, robustness, conformance to specs

## Review Checklist
- **Items reviewed**:
  - `server/id_photo_engine_minimal/crop.py` [complete]
- **Verdict**: REQUEST_CHANGES
- **Unverified claims**: none (all key claims verified via analysis and regression tests)

## Attack Surface
- **Hypotheses tested**:
  - `ZeroDivisionError` on flat fallback masks: confirmed vulnerability
  - `IndexError` on out-of-bounds coordinates: confirmed vulnerability
- **Vulnerabilities found**:
  - Major: `ZeroDivisionError` in fallback path aspect ratio computation (Line 144)
  - Minor: `IndexError` in scan loop when coordinates are outside padded dimensions (Line 78-79)
- **Untested angles**: none

## Key Decisions Made
- Audited `crop.py` and validated correctness of math for dynamic ratio, margins, and center.
- Identified crop boundary index leakage and ZeroDivisionError vulnerabilities.
- Verified local mockups using regression test runner.
- Recommended `REQUEST_CHANGES` to fix the safety bugs.

## Artifact Index
- C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\reviewer_crop_1\handoff.md — Handoff and review report
