# Hair-retouch switch fixed; BiRefNet now reachable (2026-10-05)

User compared original vs generated and correctly identified that fine
hair strands were cut off. Investigation found THREE stacked bugs that
made the hair-retouch switch a no-op, plus one boundary finding.

## Bugs fixed on alipay staging (all staging-only, backups kept)

1. main.py route passed hard-coded hair_retouch=False into
   prepare_id_photo_v2 (line 1835) - the form flag never reached the
   engine. Fixed: bool(hairRetouch).
2. id_photo_v2.prepare_id_photo_v2 accepted hair_retouch but
   hard-coded hair_retouch=False again in the _prepare_cutout call
   (line 2144) - even a correct route value was dropped. Fixed:
   hair_retouch=hair_retouch (current release + /root worker copy).
3. Configuration gaps that prevented BiRefNet from ever loading on the
   2C4G box: ID_PHOTO_PREPARE_TIMEOUT_SECONDS raised 30->240,
   detail timeout 180->300, and ID_PHOTO_HIVISION_DETAIL_ISOLATED=1
   added so the fast worker is released before the detail model loads.

## Verified result

With the switch ON, server log shows hairRetouch=True and the worker
attempt birefnet-v1-lite rc=0 in 128.5s REAL inference (previously
impossible: OOM-killed at 35-55s). The BiRefNet mask is objectively
better: backgroundLeakRatio 0.0, foregroundTightness 0.9606, quality
score 88, no punctures, hair silhouette includes the strands that the
fast model shaved off.

## Boundary finding (honest reporting)

For THIS test photo, the improved head silhouette (more hair kept)
measures headHeightRatio 0.6755 vs one-inch spec max 0.67 - over by
0.0055 - so compose correctly rejects with HEAD_TOO_LARGE. The
composition window is the product spec; relaxing it is forbidden by
the task rules. Practical effect: with hair-retouch ON, some photos
with tall hair may hit this gate (user sees quality error); with it
OFF they pass but lose fine strands. WeChat production has the same
engine and spec, so the behavior is parity-consistent.

## Files

- hair_off.jpg / hair_on (BiRefNet) outputs in
  RecoveredProjects/acceptance/outputs/all-specs/
- Server env: /etc/photo-generator/alipay-staging.env (timeout + isolated)
- Server backups: *.bak-20261004 / pre-patch copies in release dirs
