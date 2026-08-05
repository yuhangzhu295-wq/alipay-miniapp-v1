# Watermark Remove Scan Report

- Base URL: `http://127.0.0.1:8000`
- Backend health: PASS
- Source image: `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\reports\current-fixes\watermark\source\synthetic-watermark-source.jpg`
- Mask ratio: `0.174051`
- Overall: PASS

## Static Checks
- PASS: scan chip removed
- PASS: scan panel removed
- PASS: frontend scan API removed
- PASS: page scan state removed
- PASS: old scan mode degrades
- PASS: fast mode uses quick endpoint
- PASS: manual and stamp remain

## Endpoint Checks
- manual: PASS status=200 costMs=120 output=C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\reports\current-fixes\watermark\output\synthetic-watermark-source-manual.jpg
- quick: PASS status=200 costMs=69 output=C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\reports\current-fixes\watermark\output\synthetic-watermark-source-quick.jpg
- hd: PASS status=200 costMs=7974 output=C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\reports\current-fixes\watermark\output\synthetic-watermark-source-hd.jpg
