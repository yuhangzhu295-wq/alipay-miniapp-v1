# FAST Without Synchronous DETAIL

- Base URL: `http://127.0.0.1:8000`
- Runs: 30
- P50: 795ms
- P95: 910ms
- Maximum: 911ms
- Synchronous DETAIL count: 0
- Over 30 seconds: 0
- Status: **PASS**

| File | HTTP | Client ms | Model | FAST status | DETAIL fallback |
| --- | ---: | ---: | --- | --- | --- |
| `6a83d1e010f6e9ed8c35af94f0c33936.jpg` | 400 | 729 | hivision_modnet | FAST_BLOCK | False |
| `610a7b3fadac6b4452736f72b8f3a492.jpg` | 400 | 910 | hivision_modnet | FAST_BLOCK | False |
| `217139c99959fa2888673f2100612b8f.jpg` | 400 | 807 | hivision_modnet | FAST_BLOCK | False |
| `source.png` | 400 | 788 | hivision_modnet | FAST_BLOCK | False |
| `source.png` | 200 | 346 | hivision_modnet | FAST_PASS | False |
| `source.png` | 400 | 882 | hivision_modnet | FAST_BLOCK | False |
| `source.png` | 400 | 829 | hivision_modnet | FAST_BLOCK | False |
| `source.png` | 400 | 804 | hivision_modnet | FAST_BLOCK | False |
| `source.png` | 400 | 783 | hivision_modnet | FAST_BLOCK | False |
| `source.png` | 200 | 748 | hivision_modnet | FAST_WARNING | False |
| `source.png` | 400 | 739 | hivision_modnet | FAST_BLOCK | False |
| `source.jpg` | 400 | 778 | hivision_modnet | FAST_BLOCK | False |
| `source.jpg` | 200 | 856 | hivision_modnet | FAST_WARNING | False |
| `source.jpg` | 400 | 780 | hivision_modnet | FAST_BLOCK | False |
| `source.jpg` | 400 | 750 | hivision_modnet | FAST_BLOCK | False |
| `source.jpg` | 200 | 489 | hivision_modnet | FAST_PASS | False |
| `source.jpg` | 400 | 817 | hivision_modnet | FAST_BLOCK | False |
| `source.jpg` | 200 | 864 | hivision_modnet | FAST_WARNING | False |
| `abnormal_background_kept_01_normalized.png` | 400 | 860 | hivision_modnet | FAST_BLOCK | False |
| `abnormal_small_01_normalized.png` | 200 | 341 | hivision_modnet | FAST_PASS | False |
| `auto_supplement_sample_02_01_normalized.png` | 400 | 682 | hivision_modnet | FAST_BLOCK | False |
| `auto_supplement_sample_03_01_normalized.png` | 400 | 802 | hivision_modnet | FAST_BLOCK | False |
| `auto_supplement_sample_04_01_normalized.png` | 400 | 713 | hivision_modnet | FAST_BLOCK | False |
| `auto_supplement_sample_05_01_normalized.png` | 400 | 825 | hivision_modnet | FAST_BLOCK | False |
| `auto_supplement_sample_06_01_normalized.png` | 200 | 911 | hivision_modnet | FAST_WARNING | False |
| `extra_sample_01_01_normalized.png` | 400 | 837 | hivision_modnet | FAST_BLOCK | False |
| `reference_ok_01_normalized.png` | 200 | 445 | hivision_modnet | FAST_PASS | False |
| `real_source_1.jpg` | 400 | 819 | hivision_modnet | FAST_BLOCK | False |
| `real_source_2.jpeg` | 200 | 881 | hivision_modnet | FAST_WARNING | False |
| `real_source_3.jpg` | 400 | 446 | hivision_modnet | FAST_BLOCK | False |
