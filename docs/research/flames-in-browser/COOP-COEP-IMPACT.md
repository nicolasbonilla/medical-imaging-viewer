# Cross-origin isolation (COOP/COEP) on app.mstool-ai.com — impact analysis

| | |
|---|---|
| Status | Analysis only. **`firebase.json` is NOT changed by this branch.** |
| Date | 2026-10-17 |
| Why it matters | ONNX Runtime Web can use more than one WebAssembly thread only on a *cross-origin isolated* page (`self.crossOriginIsolated === true`). Today the app is not isolated, so the in-browser FLAMeS worker runs on **1 thread**: estimated **≈ 20–42 min** per 1 mm FLAIR instead of ≈ 3–7 min with 8 threads (measured 230 s, DESIGN.md §7). |
| Method | Read-only review of `firebase.json`, `frontend/index.html`, `frontend/.env.production`, all `frontend/src` network/embedding code and the backend CORS / CORP configuration. Not tested in a browser. |

## 1. What the change would be

```json
{ "source": "**", "headers": [
  { "key": "Cross-Origin-Opener-Policy",   "value": "same-origin" },
  { "key": "Cross-Origin-Embedder-Policy", "value": "credentialless" } ] }
```

`credentialless` is preferred over `require-corp` (below). The rule must be on `"**"`, not `/index.html`:
Firebase matches headers on the request path (deep links such as `/viewer/...` are rewritten to
`index.html` but keep their path), and the module worker scripts must carry COEP themselves (Firefox enforces it).

## 2. What would break or change

| Area | Facts (file:line) | `require-corp` | `credentialless` |
|---|---|---|---|
| Sign-in | Username/password via axios, JWT in localStorage (`AuthContext.tsx:4-5`, `apiClient.ts:16-21`); WebAuthn via `navigator.credentials` (`AuthContext.tsx:180-191`, `ProfilePage.tsx:206`). No OAuth/Firebase-Auth popups, no `window.open`, no `window.opener`. | unaffected | unaffected |
| API calls | API is cross-origin (`VITE_API_BASE_URL` = Cloud Run, `.env.production:3`), always CORS with `Authorization` (`apiClient.ts:8`, `ImageViewer3D.tsx:34`, `NiivueViewer2D.tsx:40`, `useBrowserFlames.ts:63`); CORS configured in `backend/app/main.py:167-168`. NIfTI → ArrayBuffer → `blob:` for niivue; slices are `data:` URLs. | unaffected (CORS) | unaffected |
| **Document preview** | `DocumentViewer.tsx:342-346` shows PDFs in an `<iframe>` of a **GCS v4 signed URL** (`api/document.ts:252-264`, `storage_service.py:733-779`); images in `<img>` of the same kind of URL (`DocumentViewer.tsx:352-353`). GCS sends neither CORP nor COEP. | **breaks** (img and iframe) | **PDF iframe breaks** (a cross-origin iframe must itself send COEP); `<img>` works (signed URL needs no cookies) |
| Google Fonts | `index.html:8-10` loads `fonts.googleapis.com` CSS without `crossorigin` (no-cors). | unknown — needs `CORP: cross-origin` from Google (not verified) | unaffected |
| Workers / WASM / models | Same-origin module workers (`useEdgeAI.ts:76-77`, `useBrowserFlames.ts:66`); ORT wasm bundled locally (`flamesInBrowser.worker.ts` `wasmPaths`); models same-origin (`/models/...`). A cross-origin `VITE_FLAMES_MODEL_URL` would need CORS. | unaffected if workers get the header | unaffected |
| Backend CORP | At STRICT/PARANOID security level the API sends `Cross-Origin-Resource-Policy: same-origin` (`tls_enforcement.py:275-278`); CORP only applies to no-cors loads, and no page loads the API that way. | unaffected | unaffected |
| Downloads (`target=_blank` anchors) | Navigations, not subresources. | unaffected | unaffected |
| Service worker / analytics / third-party iframes | None in the app. | — | — |
| Behaviour change | Edge-AI and FLAMeS workers would start using several threads (`self.crossOriginIsolated` checks); FLAMeS provenance records the thread count. Numerically the same model; results were bit-identical between 8-thread browser and Node runs (DESIGN.md §7.1), but a multi-thread run in the deployed app is **not yet verified**. | needs testing | needs testing |

## 3. Recommendation (for the owner; nothing is deployed)

1. Before any header change, fix the one real breakage: make `DocumentViewer` fetch the signed URL with `fetch()`
   (CORS must then be enabled on the GCS bucket for the app origin) and display a `blob:` URL — or keep the
   PDF preview on a non-isolated route. Until then COOP/COEP would break PDF previews.
2. Then add the two headers with `credentialless` on `"**"` in a **separate, tested change** (staging channel):
   check login, WebAuthn, document preview, fonts, 2D/3D viewer, Edge-AI badge, and that
   `crossOriginIsolated === true` in the console.
3. Verify the FLAMeS parity again in the isolated deployed app (multi-thread) before relying on the shorter time.

## 4. What the prototype does meanwhile (this branch)

* Before starting, the card states the expected duration for **this** page (`runtimeEstimate.ts`):
  "About 20–42 minutes: this page can use only 1 processor thread (estimate, not measured)" when not isolated.
* During the run it shows the elapsed time next to the expected range.
* **Cancel** is always available; it only terminates the worker and never touches the open segmentation
  (test `useBrowserFlames.cancel.test.tsx`). The clinician can keep working while it runs.
