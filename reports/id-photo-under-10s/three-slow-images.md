# FAST Without Synchronous DETAIL

- Base URL: `http://127.0.0.1:8000`
- Runs: 6
- P50: 1610ms
- P95: 1706ms
- Maximum: 1706ms
- Synchronous DETAIL count: 0
- Over 30 seconds: 0
- Status: **PASS**

| File | HTTP | Client ms | Model | FAST status | DETAIL fallback |
| --- | ---: | ---: | --- | --- | --- |
| `6a83d1e010f6e9ed8c35af94f0c33936.jpg` | 200 | 719 | hivision_modnet | FAST_WARNING | False |
| `610a7b3fadac6b4452736f72b8f3a492.jpg` | 200 | 1706 | modnet_photographic_portrait_matting | FAST_WARNING | False |
| `217139c99959fa2888673f2100612b8f.jpg` | 200 | 1603 | modnet_photographic_portrait_matting | FAST_WARNING | False |
| `6a83d1e010f6e9ed8c35af94f0c33936.jpg` | 200 | 743 | hivision_modnet | FAST_WARNING | False |
| `610a7b3fadac6b4452736f72b8f3a492.jpg` | 200 | 1705 | modnet_photographic_portrait_matting | FAST_WARNING | False |
| `217139c99959fa2888673f2100612b8f.jpg` | 200 | 1617 | modnet_photographic_portrait_matting | FAST_WARNING | False |
