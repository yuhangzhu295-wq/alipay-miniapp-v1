# IOPaint Thread A/B

Each option used `torch.set_num_interop_threads(1)` and matching service-scoped OMP, MKL, OpenBLAS, and NumExpr thread counts. The warmed 384x256 invoice fixture ran 20 times per option.

| Threads | Inference P50 | Inference P95 | Wall P95 | CPU ticks | RSS after | Swap after |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 2.595 s | 2.625 s | 2.797 s | 5527 | 690.8 MiB | 0 MiB |
| 2 | 1.444 s | 1.466 s | 1.621 s | 6121 | 690.4 MiB | 0 MiB |
| 4 | 1.392 s | 1.411 s | 1.580 s | 11438 | 764.2 MiB | 0 MiB |

The retained two-ROI invoice added a realistic tie-breaker: 2-thread client P50 was 4.308 s, while 4-thread client P50 was 3.186 s. Four threads therefore provide the lowest real P95/P50 while remaining stable on the verified 4-core, 3.6 GiB host with no process Swap.

Selected: 4 threads, interop 1, scoped only to `iopaint.service`.

Status: PASS.
