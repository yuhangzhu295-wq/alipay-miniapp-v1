# ROI Components A/B

The original implementation used one global bounding rectangle for all marks. On the retained 1495x999 invoice, two distant marks became a 1422x935 ROI covering 88.5226% of the image. Five production requests had LaMa P50 18.815 s and client P50 20.005 s.

The optimized implementation builds an 8-bit mask, filters connected-component noise, merges only nearby regions, and caps grouped ROIs at two. The same marks became two ROIs: 232x188 and 248x198, both with 64 px context. Five production requests had LaMa inference P50 1.600 s and client P50 3.186 s.

Unit scenarios passed for one small mark, two near marks, two far marks, top and bottom marks, many small marks, and one large mark. `lamaCallCount` stayed at or below two and independent outside-ROI differences stayed zero.

Status: PASS.
