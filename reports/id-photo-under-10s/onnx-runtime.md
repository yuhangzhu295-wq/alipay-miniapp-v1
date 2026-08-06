# ONNX Runtime Selection

- Cloud CPU: `AMD EPYC 7K62`; OpenVINO was explicitly skipped and
  `onnxruntime-openvino` was not installed.
- Provider: `CPUExecutionProvider`.
- Execution mode: `ORT_SEQUENTIAL`.
- Graph optimization: `ORT_ENABLE_ALL`.
- Inter-op threads: `1`.
- Selected intra-op threads: `2`.

## A/B

| Environment | Intra-op | P50 | P95 | Max | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| Local isolated workload | 1 | n/a | 542 ms workload | n/a | slower |
| Local isolated workload | 2 | n/a | 389 ms workload | n/a | selected |
| Cloud 23-request mixed workload | 1 | 3381 ms | 4411 ms | 4471 ms | slower P95 |
| Cloud 23-request mixed workload | 2 | 3050 ms | 4278 ms | 4511 ms | selected |

The selected Worker starts with both FAST sessions warmed. Production health
reported warmup `940 ms`, resident RSS `544.6 MB`, both sessions loaded, and no
model load in warm requests.

Status: **PASS**.
