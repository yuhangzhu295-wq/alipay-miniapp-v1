# Four-Level FAST Quality Gate

| Final state | Behavior |
| --- | --- |
| `FAST_PASS` | Complete subject and clean background; return immediately. |
| `FAST_REPAIRABLE` | Apply one bounded small-hole repair, then return. |
| `FAST_WARNING` | Return a usable fast result and optionally recommend asynchronous DETAIL. |
| `FAST_BLOCK` | Reject only severe missing subject, large holes/background retention, multiple/non-human subjects, severe pose/occlusion, or two unusable FAST candidates. |

`FAST_RISK` is an internal routing signal, not a final user-visible state. Mild
hair aliasing, small edge contamination, tiny isolated holes, and usable
semi-transparent edges do not become `FAST_BLOCK`.

## Verification

- Production 30-image distribution: PASS 3, REPAIRABLE 4, WARNING 23, BLOCK 0.
- Ten negative samples: false PASS 0/10. Non-human, object, landscape,
  multi-person, side-face, occluded, tiny-face, missing-shoulder, and blurred
  inputs returned professional validation errors.
- Three specified difficult images all returned usable fast results without
  synchronous DETAIL.
- Visual A/B inspection covered hair, ears, shoulders, clothing, subject holes,
  retained background, and edge halo. No large subject loss or rectangular
  transparency hole was accepted.

Status: **PASS**.
