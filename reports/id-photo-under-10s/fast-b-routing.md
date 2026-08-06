# FAST-B Routing

- FAST-A: `hivision_modnet`.
- FAST-B: `modnet_photographic_portrait_matting`.
- Routing is sequential and content-risk based. FAST-B runs only after FAST-A
  is internally classified `FAST_RISK`; neither filename nor fixed pixel rules
  participate in routing.
- A `FAST_PASS`, `FAST_REPAIRABLE`, or usable `FAST_WARNING` returns without
  synchronous DETAIL. `FAST_BLOCK` is final only when both FAST candidates are
  unusable.
- Both ONNX sessions remain resident. The 30-image production run recorded
  `sessionReused=true` and `modelLoadMs=0` for all 30 warm requests.

## Evidence

- Three specified images: FAST-A won 1 pair and FAST-B won 2 pairs. Visual
  review found FAST-B materially cleaner on the hat/raised-arms and
  tree/light-clothing cases while FAST-A remained better on the long-hair case.
- Local qualified corpus: 30/30 usable, FAST-A selected 20, FAST-B selected 10,
  FAST-B triggered 15, FAST_BLOCK 0, synchronous BiRefNet 0.
- Production qualified corpus: 30/30 usable, FAST-A selected 20, FAST-B selected
  10, FAST-B triggered 15, FAST_BLOCK 0, synchronous BiRefNet 0.

Status: **PASS**.
