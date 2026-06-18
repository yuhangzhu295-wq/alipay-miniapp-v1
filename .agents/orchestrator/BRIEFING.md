# BRIEFING — 2026-06-18T20:23:49+08:00

## Mission
Fix ID photo generation quality (aliasing/jagged edges) and enforce Mainland China ID photo standards.

## 🔒 My Identity
- Archetype: Project Orchestrator
- Roles: orchestrator, user_liaison, human_reporter, successor
- Working directory: C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\orchestrator
- Original parent: main agent
- Original parent conversation ID: 11037240-ffd6-401e-83a1-c956dc4a1ba7

## 🔒 My Workflow
- **Pattern**: Project
- **Scope document**: C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\PROJECT.md
1. **Decompose**: Decompose the quality improvement and standard enforcement work into focused milestones.
2. **Dispatch & Execute**:
   - **Direct (iteration loop)**: Spawn Explorer to analyze the issues, Worker to implement changes, Reviewer to check logic/regression, Challenger to empirically verify, and Auditor to perform final integrity check.
3. **On failure** (in this order):
   - Retry: nudge stuck agent or re-send task
   - Replace: spawn fresh agent with partial progress
   - Skip: proceed without (only if non-critical)
   - Redistribute: split stuck agent's remaining work
   - Redesign: re-partition decomposition
   - Escalate: report to parent (sub-orchestrators only, last resort)
4. **Succession**: Self-succeed at spawn count 16. On succession, write handoff.md, spawn successor.
- **Work items**:
  1. Decompose & Audit current status [pending]
  2. Implement anti-aliasing & cleanup [pending]
  3. Implement Mainland China cropping standard [pending]
  4. Run E2E and regression testing [pending]
- **Current phase**: 1
- **Current focus**: Decompose & Audit current status

## 🔒 Key Constraints
- NEVER write, modify, or create source code files directly.
- NEVER run build/test commands yourself — require workers to do so.
- You MAY use file-editing tools ONLY for metadata/state files (.md) in your .agents/ folder.
- Never reuse a subagent after it has delivered its handoff — always spawn fresh.

## Current Parent
- Conversation ID: 11037240-ffd6-401e-83a1-c956dc4a1ba7
- Updated: not yet

## Key Decisions Made
- [TBD]

## Team Roster
| Agent | Type | Work Item | Status | Conv ID |
|-------|------|-----------|--------|---------|
| explorer_audit_1 | teamwork_preview_explorer | Environment audit & initial verification | completed | 1af8929d-575a-47c1-bf59-b77209769d7a |
| worker_implement_1 | teamwork_preview_worker | Implement anti-aliasing & Mainland China cropping | completed | fee055c1-6d75-4a10-91d7-b9b0a12868c9 |
| reviewer_1 | teamwork_preview_reviewer | Run full verification and review code correctness | in-progress | 6c11666a-d6ac-42f3-9452-b68a60dfe12a |

## Succession Status
- Succession required: no
- Spawn count: 3 / 16
- Pending subagents: 6c11666a-d6ac-42f3-9452-b68a60dfe12a
- Predecessor: none
- Successor: not yet spawned

## Active Timers
- Heartbeat cron: task-23
- Safety timer: none
- On succession: kill all timers before spawning successor
- On context truncation: run `manage_task(Action="list")` — re-create if missing

## Artifact Index
- C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\orchestrator\ORIGINAL_REQUEST.md — Verbatim user request record.
