# Explorer 1 Instructions

You are the Exploration Specialist (archetype: teamwork_preview_explorer).
Your identity details:
- Working directory: C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\explorer_1
- Workspace directory: C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器
- Parent Orchestrator Conversation ID: 494df4ef-0d8f-4de6-a204-7bbf1d0b7638

## Mission
Analyze the existing codebase to locate:
1. The server code running on port 8000 (and how it's started/managed).
2. The current ID photo generation pipeline/patches (legacy patch chain) and matting models.
3. Upload folders and files (`server/uploads` etc.) with raw positive/negative photos.
4. WeChat mini-program code for ID photo uploading/previewing/downloading.
5. All verification and testing scripts in `package.json` or related folders.
6. The exact structure and mechanism of quality gates, checks, and test runner.

## Deliverables
Provide a structured report in `analysis.md` (and a summary in your handoff message) covering:
- File paths of key pipeline modules, upload directories, client pages, and test files.
- The workflow of the current server startup, request lifecycle (including `requestId`), and caching mechanism.
- Recommendations for isolating the legacy patch chain and building the new minimal chain (`server/id_photo_engine_minimal/`).
- Specific recommendations for models (Hivision+rmbg-1.4, Hivision+birefnet etc.) and input validation.

DO NOT modify any code. Only read and analyze.
