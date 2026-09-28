# MSTool-AI: SOUP Bill of Materials

## Software of Unknown Provenance — Complete Inventory

**Document ID**: SOUP-001 | **Version**: 1.1 | **Date**: September 28, 2026 (v1.0: April 12, 2026)

| Version | Date | Author | Change |
|---------|------|--------|--------|
| 1.0 | 2026-04-12 | Development Team | Initial release |
| 1.1 | 2026-09-28 | Development Team | CAPA-006 (HAZ-005). (a) SOUP-BE-020 nilearn reclassified B → **C**. It resamples the MSMask atlas zone map for the Class C MAGNIMS region classifier. Purpose was "Brain atlas"; version was "0.10.0+". Recorded as not pinned (`>=0.10.0`), with open action CAPA-006 PA-6.5; `backend/requirements.txt` not changed. (b) SOUP-BE-025 added: the MSMask atlas data file, a Class C input that had no SOUP or provenance entry. (c) Summary recounted from the tables. v1.0 stated Class B 20 / Class A 10; the tables held 21 / 9. |

---

## Frontend SOUP Items

| SOUP ID | Name | Version | Manufacturer | License | Safety Class | Purpose | Known Anomalies |
|---------|------|---------|-------------|---------|-------------|---------|----------------|
| SOUP-FE-001 | React | 18.3.1 | Meta Platforms | MIT | B | UI rendering framework | None known (2026-04) |
| SOUP-FE-002 | TypeScript | 5.6.2 | Microsoft | Apache-2.0 | A | Build-time type checking | None known |
| SOUP-FE-003 | Vite | 5.4.8 | Evan You / Vite Team | MIT | A | Build tool (dev/production) | None known |
| SOUP-FE-004 | Zustand | 4.5.5 | Daishi Kato | MIT | B | State management | None known |
| SOUP-FE-005 | TanStack React Query | 5.56.2 | Tanner Linsley | MIT | B | Server state caching | None known |
| SOUP-FE-006 | NiiVue | 0.67.0 | NiiVue Contributors | BSD-2 | B | WebGL2 NIfTI volume rendering | None known |
| SOUP-FE-007 | Three.js | 0.169.0 | Three.js Contributors | MIT | B | 3D WebGL scene management | None known |
| SOUP-FE-008 | ONNX Runtime Web | 1.21.0 | Microsoft | MIT | **C** | Browser AI inference (WebGPU/WASM) | None known |
| SOUP-FE-009 | Axios | 1.7.7 | Matt Zabriskie | MIT | B | HTTP client | None known |
| SOUP-FE-010 | Tailwind CSS | 3.4.13 | Tailwind Labs | MIT | A | Styling | None known |
| SOUP-FE-011 | Framer Motion | 12.23 | Framer | MIT | A | UI animation | None known |
| SOUP-FE-012 | i18next | 25.6.3 | i18next contributors | MIT | A | Internationalization | None known |
| SOUP-FE-013 | Lucide React | 0.447.0 | Lucide contributors | ISC | A | Icons | None known |

## Backend SOUP Items

| SOUP ID | Name | Version | Manufacturer | License | Safety Class | Purpose | Known Anomalies |
|---------|------|---------|-------------|---------|-------------|---------|----------------|
| SOUP-BE-001 | FastAPI | 0.115.0 | Sebastian Ramirez | MIT | B | REST API framework | None known |
| SOUP-BE-002 | Python | 3.11 | Python Software Foundation | PSF-2.0 | B | Runtime environment | None known |
| SOUP-BE-003 | Uvicorn | 0.32.0 | Encode | BSD-3 | B | ASGI server | None known |
| SOUP-BE-004 | nibabel | 5.3.0 | NiBabel Contributors | MIT | **C** | NIfTI file I/O | None known |
| SOUP-BE-005 | pydicom | 2.4.4 | pydicom contributors | MIT | **C** | DICOM file parsing | None known |
| SOUP-BE-006 | SimpleITK | 2.3.1 | Insight Software Consortium | Apache-2.0 | B | Medical image processing | None known |
| SOUP-BE-007 | NumPy | 1.26.4 | NumPy Developers | BSD-3 | **C** | Array operations (volumetry) | None known |
| SOUP-BE-008 | SciPy | 1.13.1 | SciPy Developers | BSD-3 | **C** | EDT, connected components | None known |
| SOUP-BE-009 | scikit-image | 0.24.0 | scikit-image contributors | BSD-3 | B | Image analysis | None known |
| SOUP-BE-010 | OpenCV | 4.10.0 | OpenCV contributors | Apache-2.0 | B | Computer vision | None known |
| SOUP-BE-011 | Anthropic SDK | 0.44.0 | Anthropic | MIT | **C** | Claude API (report generation) | None known |
| SOUP-BE-012 | Google Cloud AI Platform | 1.136.0 | Google | Apache-2.0 | **C** | Vertex AI inference | None known |
| SOUP-BE-013 | WebAuthn (py) | 2.7.1 | Duo Labs | BSD-3 | B | FIDO2 authentication | None known |
| SOUP-BE-014 | FastMCP | 2.3.0 | FastMCP contributors | MIT | A | MCP server framework | None known |
| SOUP-BE-015 | Firebase Admin | 7.1.0 | Google | Apache-2.0 | B | Auth, Firestore, Storage | None known |
| SOUP-BE-016 | Pydantic | 2.9.0 | Samuel Colvin | MIT | B | Data validation | None known |
| SOUP-BE-017 | python-jose | 3.3.0 | Michael Davis | MIT | B | JWT management | None known |
| SOUP-BE-018 | Argon2-cffi | 23.1.0 | Hynek Schlawack | MIT | B | Password hashing | None known |
| SOUP-BE-019 | httpx | 0.28.1 | Encode | BSD-3 | B | Async HTTP (DICOMweb) | None known |
| SOUP-BE-020 | nilearn | `>=0.10.0`, **not pinned** (the development venv resolved 0.14.1 on 2026-09-28); v1.0: "0.10.0+" | nilearn contributors | BSD-3 | **C** (B until 2026-09-28) | Resamples the MSMask atlas zone map onto the patient image grid (`nilearn.image.resample_to_img`, nearest neighbour) in `ms_region_classifier.generate_zone_map_atlas`, a Class C function (HAZ-005). This is its only live use. v1.0: "Brain atlas" | None known. **Open action (CAPA-006 PA-6.5)**: pin the version and review nilearn as Class C SOUP (functional and performance requirements, known anomalies). The `requirements.txt` comment "Harvard-Oxford via nilearn" is stale: it refers to `services/atlas_provider.py`, which no module imports |
| SOUP-BE-021 | matplotlib | 3.9.2 | Matplotlib Developers | PSF-2.0 | A | Visualization | None known |
| SOUP-BE-022 | pandas | 2.2.2 | pandas contributors | BSD-3 | A | Data processing | None known |
| SOUP-BE-023 | Redis (py) | 5.1.0 | Redis contributors | MIT | B | Caching | None known |
| SOUP-BE-024 | SQLAlchemy | 2.0.25 | Michael Bayer | MIT | B | ORM | None known |
| SOUP-BE-025 | MSMask atlas (data file) — `backend/data/msmask/sub-mni152_space-mni_msmask.nii.gz`, deployed as `/app/data/msmask/` (added 2026-09-28) | sha256 `2ad50b1433a040a4d5b58ac064f984211b466f83081fc5d344ff13eff56cdd0f` (277,729 bytes). Per `scripts/download_msmask.py`, extracted from the LST-AI v1.1.0 release asset `lst_data.zip` (`atlas/sub-mni152_space-mni_msmask.nii.gz`); committed 2026-02-28 (247c1b8). The committed file's origin has not been independently re-verified against the release | LST-AI (Wiltgen et al., NeuroImage: Clinical 2024; 42: 103611), github.com/CompImg/LST-AI | **To be confirmed**: not stated in the repository. The LST-AI licence is recorded as not confirmed permissive (`docs/reviews/Lesion_Segmentation_Review_2026-07.md` §7.4) | **C** | MNI152 tissue labels (1 CSF, 2 GM/cortex, 3 WM, 4 ventricles, 5 infratentorial; 193x229x193 at 1 mm, grid centre (0, -18, 18)). The MAGNIMS atlas zone map is built from it (`generate_zone_map_atlas`, HAZ-005) | None known. Its use here is an adaptation whose region accuracy has not been measured (HAZ-005). It is applied only to MNI-like grids (RC-032, REQ-SAFE-021) |

## Summary

| Category | Count |
|----------|-------|
| Total SOUP items | 38 (v1.0: 37) |
| Safety Class C | 9 (ONNX, nibabel, pydicom, NumPy, SciPy, Anthropic, Google AI, nilearn, MSMask atlas) (v1.0: 7) |
| Safety Class B | 20 (v1.0 stated 20; the v1.0 tables held 21, nilearn now C) |
| Safety Class A | 9 (v1.0 stated 10; the v1.0 tables held 9) |

**Last vulnerability review**: April 12, 2026
**Next scheduled review**: May 12, 2026

---

*SOUP anomalies are reviewed monthly using npm audit, pip-audit, and NVD database queries.*

## 6. CycloneDX Software Bill of Materials

A machine-readable SBOM in CycloneDX 1.5 format is maintained at `docs/iec62304/SBOM_CycloneDX.json`.

- Contains all SOUP items with versions and purl identifiers
- Each component tagged with IEC 62304 safety class (A/B/C)
- Updated with each major/minor release when dependencies change
- Compliant with NTIA minimum elements, EU Cybersecurity Act Annex IV
