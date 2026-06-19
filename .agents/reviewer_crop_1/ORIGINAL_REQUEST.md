## 2026-06-18T16:50:03Z
You are Reviewer 1.
Your working directory is: C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\reviewer_crop_1
Your task is to review the code correctness, completeness, and safety of the cropping implementation in `server/id_photo_engine_minimal/crop.py`.
Check that it correctly implements:
1. Dynamic 70% (strictly 65% to 75%) head ratio.
2. Hair volume mask detection.
3. Proper top margin (10%) and shoulder/clavicle bottom margins.
4. Perfect horizontal centering.
5. Adaptive sizing without hardcoded pixels.
Ensure it handles missing landmarks and falls back properly to faceBox or bounding box, handles edge conditions safely, and is robust.
Write your review report and verify commands in C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\reviewer_crop_1\handoff.md and report back.
