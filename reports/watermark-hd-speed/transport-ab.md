# Backend to IOPaint Transport A/B

The installed IOPaint 1.6.0 OpenAPI exposes `/api/v1/inpaint` as Base64 JSON. It does not expose a multipart inpaint endpoint, a shared-file adapter, or an import-stable direct model adapter.

Twenty local serialization runs on a 1024-edge fixture produced:

| Candidate | P50 | P95 | Installed endpoint support |
| --- | ---: | ---: | --- |
| Base64 JSON encode/decode | 0.216 ms | 0.263 ms | Yes |
| Multipart body construction | 0.021 ms | 0.034 ms | No |
| Temporary file write/read | 0.289 ms | 1.482 ms | No |
| Direct model adapter | n/a | n/a | No stable adapter API |

The compatible Base64 JSON path is retained with a persistent `requests.Session`, localhost `127.0.0.1`, keep-alive reuse, and separate connect/encode/HTTP/decode timings. Encoding is sub-millisecond and not the latency bottleneck.

Status: PASS.
