# ONNX Runtime Local A/B

- Scope: isolated local worker; production AMD result must be confirmed after deployment.
- Status: **PASS**
- Preliminary selection: intra-op `2`, inter-op `1`.

| Intra | Cold P95 | Warm P95 | Workload P95 | Inference P95 | Peak RSS | Swap delta |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 548.342 ms | 547.311 ms | 542.49 ms | 415.0 ms | 742.9 MB | 3.6 MB |
| 2 | 426.41 ms | 440.255 ms | 389.382 ms | 288.0 ms | 744.0 MB | 6.9 MB |
