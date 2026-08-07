# Inference Size A/B

Direct warmed IOPaint tests used the same synthetic invoice/table fixture, three runs per option.

| Variant | Wall P50 | Wall P95 | Outside changed | Residual ratio max |
| --- | ---: | ---: | ---: | ---: |
| Small 768 | 5.478 s | 5.484 s | 0 | 0.0164 |
| Small 1024 | 9.664 s | 9.731 s | 0 | 0.0247 |
| Medium 1024 | 9.770 s | 9.797 s | 0 | 0.0247 |
| Medium 1280 | 15.567 s | 15.626 s | 0 | 0.0026 |
| Large 1280 | 15.394 s | 15.456 s | 0 | 0.0026 |
| Large 1536 | 23.379 s | 24.443 s | 0 | 0.0082 |

The selected policy uses 768 for small work, 1024/1280 for medium work, and 1280/1536 only when ROI span and texture justify the cost. Scaling applies only to the inference copy; the final image is composited at the original resolution.

Raw evidence: `size-transport-ab.json`.

Status: PASS.
