# FAST-A / FAST-B verification

- Generated: `2026-08-07T00:20:04+08:00`
- Status: `PASS`
- FAST-A: `hivision_modnet`
- FAST-B: `modnet_photographic_portrait_matting`
- Shared pre-resize maximum side: `768`
- OpenVINO: skipped; this comparison uses ONNX Runtime CPUExecutionProvider.
- Automated metrics are evidence, not the final routing decision; paired visual review is mandatory.

| sample | model | reused | inference ms | total ms | leak | holes | shoulder cutoff | hair cutoff | edge transition | old-bg risk | score |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 6a83d1e010f6e9ed8c35af94f0c33936.jpg | FAST-A | False | 223.712 | 821.789 | 0.044649 | 0.000000 | 0.421802 | 0.112297 | 0.046716 | 0.032699 | 30.279 |
| 6a83d1e010f6e9ed8c35af94f0c33936.jpg | FAST-B | False | 217.097 | 817.105 | 0.043494 | 0.000493 | 0.415235 | 0.058573 | 0.067096 | 0.090422 | 26.742 |
| 610a7b3fadac6b4452736f72b8f3a492.jpg | FAST-A | True | 219.044 | 820.709 | 0.471869 | 0.024481 | 0.000000 | 0.000000 | 0.078048 | 0.135649 | 15.204 |
| 610a7b3fadac6b4452736f72b8f3a492.jpg | FAST-B | True | 219.094 | 829.364 | 0.427276 | 0.008311 | 0.000000 | 0.000000 | 0.041744 | 0.010485 | 22.718 |
| 217139c99959fa2888673f2100612b8f.jpg | FAST-A | True | 208.587 | 900.757 | 0.360023 | 0.000883 | 0.187443 | 0.001765 | 0.055601 | 0.044085 | 21.544 |
| 217139c99959fa2888673f2100612b8f.jpg | FAST-B | True | 213.901 | 899.543 | 0.354692 | 0.003501 | 0.182272 | 0.000000 | 0.051375 | 0.022246 | 22.887 |

## Automated comparison

- FAST-A mean quality score: `22.342`
- FAST-B mean quality score: `24.116`
- Pair wins: FAST-A `1`, FAST-B `2`, tie `0`.
- FAST-B eligible by automated metrics: `True`.
- Paired visual inspection: **PASS**.
- Night long-hair image: FAST-A retains the hair boundary more naturally; ears, shoulders, and clothing remain intact.
- Hat and raised-arms image: FAST-B has fewer subject holes and less retained background while preserving the hat and arms.
- Tree and light-clothing image: FAST-B has the cleaner boundary while preserving hair, ears, and shoulders.
- Production decision: run photographic MODNet sequentially only when FAST-A is classified `FAST_RISK`.

## Metric definitions

- `backgroundLeakRatio`: foreground outside the face-driven valid subject prior.
- `subjectHoleRatio`: enclosed transparent holes inside the largest foreground component.
- `shoulderCutoffRatio`: missing alpha in symmetric shoulder zones derived from the detected face.
- `hairCutoffRatio`: missing alpha in the central crown zone derived from the detected face.
- `edgeHaloRatio`: partially transparent pixels divided by nontransparent foreground pixels.
- `foregroundOldBgRatio`: maximum of retained-background, contour-complexity, and fragmented-row risk signals.
- `boundaryComplexity`: contour compactness; thin attached background structures increase it.
- `fragmentedRowRatio`: rows containing more than two disjoint foreground runs.
