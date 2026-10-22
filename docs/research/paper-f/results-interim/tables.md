### Table 1 — per cohort (primary definitions; mean over scans, 95% patient-cluster bootstrap CI)

| Cohort | Tool | Scans | Lesion F1 | False lesions / scan | Dice | Lesion recall | Predicted mL | Expert mL |
|---|---|---|---|---|---|---|---|---|
| mslesseg | FLAMeS (5 folds) | 115 | 0.769 (0.746 to 0.791) | 4.8 (3.9 to 5.7) | 0.653 (0.609 to 0.693) | 0.792 (0.765 to 0.818) | 15.51 | 11.80 |
| mslesseg | LST-AI | 114 | 0.555 (0.508 to 0.596) | 8.9 (7.4 to 10.4) | 0.393 (0.343 to 0.443) | 0.531 (0.485 to 0.575) | 9.58 | 11.83 |
| mslesseg | MindGlide | 115 | 0.542 (0.514 to 0.569) | 8.1 (7.3 to 9.0) | 0.375 (0.318 to 0.431) | 0.722 (0.682 to 0.758) | 28.41 | 11.80 |
| openms | FLAMeS (5 folds) | 10 | 0.760 (0.691 to 0.824) | 2.9 (1.2 to 5.0) | 0.661 (0.570 to 0.750) | 0.688 (0.632 to 0.745) | 9.33 | 9.97 |
| openms | LST-AI | 30 | 0.685 (0.640 to 0.726) | 8.0 (6.2 to 10.3) | 0.646 (0.570 to 0.716) | 0.647 (0.608 to 0.685) | 15.74 | 17.11 |
| openms | MindGlide | 30 | 0.494 (0.446 to 0.541) | 4.5 (3.5 to 5.6) | 0.461 (0.372 to 0.546) | 0.476 (0.408 to 0.544) | 22.76 | 17.11 |
| ms3seg | FLAMeS (5 folds) | 100 | 0.749 (0.724 to 0.772) | 8.3 (7.2 to 9.5) | 0.675 (0.653 to 0.697) | 0.826 (0.799 to 0.850) | 17.24 | 12.73 |
| ms3seg | MindGlide | 100 | 0.587 (0.560 to 0.612) | 9.6 (8.8 to 10.5) | 0.513 (0.479 to 0.545) | 0.674 (0.644 to 0.704) | 18.28 | 12.73 |
| ms3seg | MindGlide raw input | 100 | 0.584 (0.557 to 0.610) | 8.3 (7.6 to 9.1) | 0.539 (0.506 to 0.570) | 0.626 (0.595 to 0.656) | 16.36 | 12.73 |
| muslim | FLAMeS (5 folds) | 51 | 0.639 (0.594 to 0.682) | 6.5 (5.2 to 7.9) | 0.567 (0.523 to 0.609) | 0.652 (0.590 to 0.713) | 18.39 | 19.77 |
| muslim | MindGlide | 51 | 0.515 (0.476 to 0.554) | 6.9 (6.1 to 7.8) | 0.468 (0.421 to 0.514) | 0.533 (0.478 to 0.591) | 19.93 | 19.77 |
| muslim | MindGlide raw input | 51 | 0.497 (0.456 to 0.537) | 6.9 (6.2 to 7.6) | 0.474 (0.428 to 0.519) | 0.494 (0.437 to 0.552) | 17.56 | 19.77 |
| pedims | FLAMeS (5 folds) | 28 | 0.785 (0.743 to 0.824) | 5.9 (3.7 to 7.7) | 0.684 (0.619 to 0.736) | 0.796 (0.763 to 0.827) | 13.11 | 13.43 |
| pedims | MindGlide | 28 | 0.560 (0.460 to 0.658) | 5.9 (3.8 to 8.6) | 0.497 (0.390 to 0.564) | 0.572 (0.406 to 0.725) | 12.47 | 13.43 |
| pedims | MindGlide raw input | 28 | 0.534 (0.438 to 0.627) | 6.6 (4.9 to 8.6) | 0.512 (0.412 to 0.572) | 0.527 (0.374 to 0.663) | 9.80 | 13.43 |

### Table 2 — per band (cohort-weighted mean, each cohort counts once; 95% CI)

| Band | Tool | Scans | Lesion F1 | False lesions / scan | Dice |
|---|---|---|---|---|---|
| iso | FLAMeS (5 folds) | 125 | 0.765 (0.727 to 0.798) | 3.8 (2.8 to 5.0) | 0.657 (0.607 to 0.705) |
| iso | LST-AI | 144 | 0.620 (0.588 to 0.650) | 8.4 (7.2 to 9.8) | 0.520 (0.474 to 0.563) |
| iso | MindGlide | 145 | 0.518 (0.490 to 0.543) | 6.3 (5.6 to 7.0) | 0.418 (0.364 to 0.469) |
| thick | FLAMeS (5 folds) | 179 | 0.724 (0.702 to 0.745) | 6.9 (6.0 to 7.8) | 0.642 (0.614 to 0.665) |
| thick | MindGlide | 179 | 0.554 (0.517 to 0.589) | 7.5 (6.7 to 8.5) | 0.493 (0.452 to 0.522) |
| thick | MindGlide raw input | 179 | 0.538 (0.503 to 0.572) | 7.3 (6.6 to 8.0) | 0.508 (0.470 to 0.536) |
| thick_3-5.5 | FLAMeS (5 folds) | 52 | 0.702 (0.667 to 0.734) | 6.5 (5.1 to 7.7) | 0.637 (0.595 to 0.673) |
| thick_3-5.5 | MindGlide | 52 | 0.513 (0.456 to 0.569) | 6.2 (5.0 to 7.7) | 0.484 (0.417 to 0.537) |
| thick_3-5.5 | MindGlide raw input | 52 | 0.491 (0.435 to 0.544) | 6.5 (5.5 to 7.7) | 0.497 (0.435 to 0.545) |
| thick_>5.5 | FLAMeS (5 folds) | 127 | 0.703 (0.667 to 0.736) | 7.2 (6.0 to 8.4) | 0.612 (0.576 to 0.644) |
| thick_>5.5 | MindGlide | 127 | 0.573 (0.546 to 0.598) | 8.4 (7.7 to 9.2) | 0.489 (0.457 to 0.521) |
| thick_>5.5 | MindGlide raw input | 127 | 0.562 (0.531 to 0.592) | 7.9 (7.3 to 8.5) | 0.502 (0.469 to 0.534) |

### Table 3 — pre-stated comparisons available now (difference = tool minus reference)

| Family | Tool vs | Band | Outcome | Scans / patients | Difference (95% CI) | 90% CI | p | Multiplicity-adjusted p | Equivalent? |
|---|---|---|---|---|---|---|---|---|---|
| primary | MindGlide vs FLAMeS (5 folds) | thick | f1 | 179 / 160 | -0.170 (-0.206 to -0.136) | -0.200 to -0.141 | < 0.0001 | < 0.0001 (Bonferroni bound x6 (family incomplete)) | no |
| primary | MindGlide vs FLAMeS (5 folds) | thick | false_lesions | 179 / 160 | 0.569 (-0.891 to 2.212) | -0.660 to 1.967 | 0.4496 | 1.0000 (Bonferroni bound x6 (family incomplete)) | no |
| secondary | MindGlide vs FLAMeS (5 folds) | iso | f1 | 125 / 85 | -0.272 (-0.319 to -0.229) | -0.311 to -0.236 | < 0.0001 | < 0.0001 (Bonferroni bound x11 (family incomplete)) | no |
| secondary | MindGlide vs FLAMeS (5 folds) | iso | false_lesions | 125 / 85 | 3.065 (1.782 to 4.316) | 1.979 to 4.117 | < 0.0001 | < 0.0001 (Bonferroni bound x11 (family incomplete)) | no |
| secondary | LST-AI vs FLAMeS (5 folds) | iso | f1 | 124 / 85 | -0.180 (-0.212 to -0.150) | -0.208 to -0.155 | < 0.0001 | < 0.0001 (Bonferroni bound x11 (family incomplete)) | no |
| secondary | LST-AI vs FLAMeS (5 folds) | iso | false_lesions | 124 / 85 | 3.789 (2.529 to 4.945) | 2.735 to 4.774 | < 0.0001 | < 0.0001 (Bonferroni bound x11 (family incomplete)) | no |
| secondary | MindGlide vs FLAMeS (5 folds) | (tool-ref)_thick - (tool-ref)_iso | f1 | 304 / 245 | 0.102 (0.047 to 0.160) | 0.055 to 0.151 | < 0.0001 | < 0.0001 (Bonferroni bound x11 (family incomplete)) | — |
| secondary_raw_arm | MindGlide raw input vs FLAMeS (5 folds) | thick | f1 | 179 / 160 | -0.186 (-0.222 to -0.150) | -0.217 to -0.155 | < 0.0001 | < 0.0001 (Holm) | no |
| secondary_raw_arm | MindGlide raw input vs FLAMeS (5 folds) | thick | false_lesions | 179 / 160 | 0.378 (-0.940 to 1.881) | -0.734 to 1.653 | 0.5600 | 0.9856 (Holm) | no |
| secondary_raw_arm | MindGlide raw input vs MindGlide | thick | f1 | 179 / 160 | -0.016 (-0.028 to -0.004) | -0.026 to -0.006 | 0.0122 | 0.0366 (Holm) | yes |
| secondary_raw_arm | MindGlide raw input vs MindGlide | thick | false_lesions | 179 / 160 | -0.191 (-0.751 to 0.319) | -0.649 to 0.235 | 0.4928 | 0.9856 (Holm) | yes |

### Table 4 — expert lesions detected, by lesion size (pooled over scans; 95% CI)

| Band | Tool | 14-50 mm³ | 50-200 mm³ | 200-1000 mm³ | >=1000 mm³ |
|---|---|---|---|---|---|
| iso | FLAMeS (5 folds) | 0.56 (0.51–0.61; n=1209) | 0.84 (0.81–0.87; n=1519) | 0.95 (0.92–0.97; n=555) | 0.99 (0.98–1.00; n=180) |
| iso | LST-AI | 0.43 (0.39–0.47; n=1931) | 0.66 (0.61–0.71; n=1907) | 0.76 (0.71–0.81; n=667) | 0.96 (0.92–0.98; n=227) |
| iso | MindGlide | 0.34 (0.30–0.40; n=1931) | 0.62 (0.57–0.66; n=1918) | 0.86 (0.83–0.90; n=674) | 0.99 (0.97–1.00; n=228) |
| thick | FLAMeS (5 folds) | 0.49 (0.44–0.54; n=1248) | 0.79 (0.75–0.82; n=2869) | 0.90 (0.87–0.92; n=1480) | 0.97 (0.95–0.99; n=396) |
| thick | MindGlide | 0.22 (0.18–0.27; n=1248) | 0.53 (0.48–0.59; n=2869) | 0.80 (0.75–0.84; n=1480) | 0.97 (0.96–0.99; n=396) |
| thick | MindGlide raw input | 0.16 (0.13–0.20; n=1248) | 0.48 (0.43–0.54; n=2869) | 0.78 (0.74–0.83; n=1480) | 0.97 (0.96–0.99; n=396) |

### Table 5 — sensitivity analyses of the primary comparisons (no multiplicity adjustment)

| Analysis | Tool | Outcome | Scans | Difference vs FLAMeS (95% CI) |
|---|---|---|---|---|
| S1_no_size_filter | MindGlide | f1 | 179 | -0.188 (-0.217 to -0.160) |
| S2_min_3mm3 | MindGlide | f1 | 179 | -0.184 (-0.217 to -0.152) |
| S3_inplane_8conn | MindGlide | f1 | 179 | -0.153 (-0.182 to -0.127) |
| S4_complete_case | MindGlide | f1 | 179 | -0.170 (-0.206 to -0.136) |
| S6_thick_without_muslim | MindGlide | f1 | 128 | -0.194 (-0.245 to -0.145) |
| S7_scan_weighted | MindGlide | f1 | 179 | -0.161 (-0.184 to -0.140) |
| S1_no_size_filter | MindGlide | false_lesions | 179 | 2.418 (0.104 to 5.064) |
| S2_min_3mm3 | MindGlide | false_lesions | 179 | 1.930 (-0.118 to 4.291) |
| S3_inplane_8conn | MindGlide | false_lesions | 179 | 8.089 (4.506 to 12.350) |
| S4_complete_case | MindGlide | false_lesions | 179 | 0.569 (-0.891 to 2.212) |
| S6_thick_without_muslim | MindGlide | false_lesions | 128 | 0.637 (-1.404 to 2.957) |
| S7_scan_weighted | MindGlide | false_lesions | 179 | 0.849 (-0.344 to 2.012) |
| S5_iso_with_flames_training_cases | MindGlide | f1 | 145 | -0.258 (-0.286 to -0.231) |
| S5_iso_with_flames_training_cases | LST-AI | f1 | 144 | -0.156 (-0.180 to -0.133) |

### Table 6 — exploratory second-opinion analyses (7.5)

| Analysis | Tool | Band | Result |
|---|---|---|---|
| E1 AUROC: disagreement flags FLAMeS lesion F1 < 0.5 | MindGlide | iso | 0.813 (2 poor of 125 scans) |
| E2 confirmed-lesions filter minus FLAMeS alone | MindGlide | iso | F1 -0.106 (-0.152 to -0.065); false lesions -1.6 (-2.4 to -0.9) |
| E1 AUROC: disagreement flags FLAMeS lesion F1 < 0.5 | MindGlide | thick | 0.779 (14 poor of 179 scans) |
| E2 confirmed-lesions filter minus FLAMeS alone | MindGlide | thick | F1 -0.074 (-0.111 to -0.040); false lesions -3.8 (-4.7 to -2.8) |
| E1 AUROC: disagreement flags FLAMeS lesion F1 < 0.5 | LST-AI | iso | 0.803 (2 poor of 124 scans) |
| E2 confirmed-lesions filter minus FLAMeS alone | LST-AI | iso | F1 -0.033 (-0.057 to -0.015); false lesions -1.8 (-2.3 to -1.3) |

### Table 7 — what each tool contributed (primary variant rows)

| Tool | missing | ok |
|---|---|---|
| FLAMeS (5 folds) | 0 | 324 |
| LST-AI | 180 | 144 |
| MindGlide | 0 | 324 |
| WMH-SynthSeg | 324 | 0 |
| SAMSEG | 324 | 0 |
| MindGlide raw input | 145 | 179 |
