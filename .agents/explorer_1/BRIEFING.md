# BRIEFING — 2026-06-17T16:24:10Z

## Mission
Analyze the existing ID photo generator codebase to locate server, generation pipeline/patches, upload folders, WeChat mini-program, and tests.

## 🔒 My Identity
- Archetype: teamwork_preview_explorer
- Roles: Exploration Specialist
- Working directory: C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\explorer_1
- Original parent: 494df4ef-0d8f-4de6-a204-7bbf1d0b7638
- Milestone: Codebase Exploration and Pipeline Analysis

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- CODE_ONLY network mode: No external websites or services, no HTTP clients targeting external URLs

## Current Parent
- Conversation ID: 494df4ef-0d8f-4de6-a204-7bbf1d0b7638
- Updated: not yet

## Investigation State
- **Explored paths**:
  - `server/main.py`
  - `server/id_photo_engines/engine_manager.py`
  - `server/id_photo_engines/hivision/adapter.py`
  - `server/id_photo_engines/hivision/runner.py`
  - `server/services/id_photo_v2.py`
  - `server/services/portrait_matting.py`
  - `server/services/id_photo_composer.py`
  - `server/services/portrait_quality.py`
  - `server/scripts/verify_all.py`
  - `server/scripts/verify_id_photo_chain.py`
  - `reports/id-photo-samples/input`
  - `reports/id-photo-samples/negative`
  - `pages/` (generate, result, photos, specs, tools, tool-detail)
- **Key findings**:
  - Located the FastAPI backend running on port 8000 (uvicorn) and the optional IOPaint backend on port 8081.
  - Traced request lifecycle of the two-step E2E generation pipeline (`/api/id-photo/prepare` and `/api/id-photo/compose`) and the `request_id` tracking.
  - Explored in-memory dict caching (`PREPARE_CACHE`) with a 24h TTL and active hourly file cleanup.
  - Located sample inputs: 202 positive pictures in `reports/id-photo-samples/input` and 12 negative pictures in `reports/id-photo-samples/negative`.
  - Discovered 58 verification scripts in `server/scripts/`, coordinated by `verify_all.py` as the main verifier.
- **Unexplored areas**:
  - Outfit templates overlay rendering mechanics.
  - Mini-program canvas layout logic for other toolkit options.

## Key Decisions Made
- Analyzed the legacy patch chain and documented path decoupling recommendations for `id_photo_engine_minimal/`.

## Artifact Index
- analysis.md — Main exploration analysis report
- handoff.md — Agent handoff report
