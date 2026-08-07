# Quality Regression

Five production-domain sample classes passed: retained user invoice, 640x480, 1920x1080, 3200x2200 scan, and 4096x3072. Coverage includes small/medium/large masks, single/near/far ROIs, text, tables, stamp, QR-like detail, complex background, retry, and continued local repair.

Every sample ran quick regression, HD, HD retry, continued HD repair, preview fetch, and download fetch. HD always reported LaMa, no fallback, warm model, original dimensions, and zero independently measured changes outside ROI.

Synthetic watermarked fixtures were compared with clean references. Initial HD relative MAE values were 0.0619 (small), 0.0216 (Full HD), 0.1635 (scan/stamp), and 0.0496 (4K), all lower than their watermarked inputs. The first unrealistic solid 4K rectangle fixture produced visible blur and was rejected rather than counted; the replacement uses real brush-shaped translucent marks and passed both metrics and visual inspection.

Preview and repeated download SHA-256 values matched server `fileHash` for every matrix operation.

Status: PASS.
