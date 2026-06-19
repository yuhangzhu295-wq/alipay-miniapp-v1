# BRIEFING — 2026-06-19T14:50:00+08:00

## Mission
Implement the frontend layout download option feature in the backend and frontend codebase.

## 🔒 My Identity
- Archetype: implementer/qa/specialist
- Roles: implementer, qa, specialist
- Working directory: C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\worker_layout_download_1
- Original parent: 5f758f22-cb05-4822-bdcd-35b830bf9313
- Milestone: implement frontend layout download option

## 🔒 Key Constraints
- CODE_ONLY network mode. No external HTTP clients/calls.
- Do not cheat, do not hardcode test results.
- Write only to our folder for metadata, read any folder.

## Current Parent
- Conversation ID: 5f758f22-cb05-4822-bdcd-35b830bf9313
- Updated: not yet

## Task Summary
- **What to build**: Add `"layoutUrl"` to `/api/id-photo/compose` backend endpoint, support layoutUrl handling in API wrapper, integrate layoutUrl in generate.js and result.js, support action sheet for choosing between single/layout photo download, and mock this behavior in automated tests.
- **Success criteria**: Verification tests pass: `npm run verify:frontend-ui` and `npm run verify:full-business-flow` pass.
- **Interface contracts**: PROJECT.md / user request requirements.
- **Code layout**: Backend in `server/`, frontend pages in `pages/`, utils in `utils/`.

## Key Decisions Made
- [TBD]

## Artifact Index
- C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\worker_layout_download_1\ORIGINAL_REQUEST.md — Original request
- C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\worker_layout_download_1\progress.md — Progress tracker
