# ROI Padding A/B

The implementation chooses context from brush size, mask span, mask fill, local Laplacian texture, and image boundaries. It does not contain image-specific coordinates.

| Context class | Padding | Evidence |
| --- | ---: | --- |
| Small/simple | 32-64 px | Small isolated controls and retained invoice ROIs used 64 px. |
| Normal text/table | 96 px | Small text, Full HD near marks, and scan/stamp matrix samples used 96 px. |
| Complex/large span | 108-128 px | 4K large-span sample used 108 px; large unit and continued 4K repair used 128 px. |

All matrix outputs kept their original dimensions and independently measured zero changed pixels outside the returned ROI boxes. Visual inspection showed table lines, QR-like detail, and the unpainted stamp remained intact.

Status: PASS.
