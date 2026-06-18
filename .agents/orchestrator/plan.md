# Project Plan: Fix ID Photo Quality & Mainland China Standards

## Objectives
1. Implement anti-aliased high-resolution alpha in `alpha_cleanup.py`.
2. Implement Mainland China ID photo cropping standard in `crop.py`.
3. Ensure strict isolation: all modifications inside `server/id_photo_engine_minimal`.
4. Validate edge quality, proportions, and run all regression verification scripts.

## Milestones
### Milestone 1: Environment Audit & Initial Verification
- Run current regression test suite to establish a baseline.
- Audit if the service on port 8000 is running and how it behaves.
- **Verification**: Command outputs from worker indicating current status.

### Milestone 2: Anti-Aliased High-Resolution Alpha (`alpha_cleanup.py`)
- Modify `alpha_cleanup.py` to preserve soft alpha edges from the matting model.
- Filter out isolated noise and disconnected background components using connected components, without hard-binarizing.
- **Verification**: Programmatic verify of non-binary alpha gradients (values between 10 and 245) and visually smooth hair/shoulder edges.

### Milestone 3: Mainland China ID Photo Cropping Standard (`crop.py`)
- Modify `crop.py` using MediaPipe/OpenCV landmarks (from `detect_face` output).
- Scale/crop photo so face is horizontally centered and head height (chin to crown) is approximately 2/3 of the total height.
- Ensure shoulders are naturally visible.
- **Verification**: Visual alignment check and programmatic head ratio check.

### Milestone 4: Final Testing & Regression Verification
- Run `npm run verify:full-business-flow` (which calls `verify_id_photo_full_business_flow.py`) and other regression tests.
- Ensure no regressions across other tools.
- **Verification**: Regression test logs passing 100%.
