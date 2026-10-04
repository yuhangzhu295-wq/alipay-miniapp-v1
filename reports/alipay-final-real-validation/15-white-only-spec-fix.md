# White-only spec fix on staging (2026-10-04)

The all-spec sweep (see
RecoveredProjects/acceptance/outputs/all-specs/verdict.md) exposed a
real backend bug: every white_only spec (driver-license-cn, id-card-cn,
social-security-cn, passport-cn, exit-entry-cn, teacher-exam white
default, resume-headshot gray fallback path) could never pass PREPARE
on either platform because three code sites hard-coded blue.

## Symptom

prepare returns 400 (POSE_NOT_FRONTAL / QUALITY_FAILED) even for a
photo whose matting scores 100/100 with zero fail reasons. The payload's
finalIdPhotoValidation.documentStandard.backgroundPolicyPass=false with
background.expectedRgb=[26,115,232] (blue) reveals the real cause.

## Root cause chain

1. v2 fast-quality probe composes the probe with BG_COLORS["blue"]
   regardless of spec -> white_only check fails.
2. id_photo_quality expected_rgb fallback ignores named defaultBg
   ('white' is not hex -> falls back to #1A73E8).
3. main.py build_edge_id_photo_foreground composes the edge foreground
   with hard-coded #1a73e8 and fails the same check during prepare.

## Staging-only fixes applied (with server-side backups)

- BG_COLORS.get(spec.get("defaultBg"), BG_COLORS["blue"]) at both probe
  sites in id_photo_v2.py (release copy + /root worker copy).
- defaultBg -> hex mapping before _hex_to_rgb in id_photo_quality.py
  (release copy + /root worker copy).
- edge foreground now derives spec defaultBg from PREPARE_CACHE and
  composes + un-composites with the matching color (main.py).

## Verification

- Real Pexels photo cand_1: prepare 200 -> compose white -> download ->
  judge PASS (260x378 exact, pure white bg, face ok). File:
  all-specs/driver_cand_1.jpg.
- All 14 client specs now PASS (summary.json updated).
- Production (WeChat) untouched; no push, no merge, no master changes.
