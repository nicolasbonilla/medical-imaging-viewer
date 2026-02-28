# Plan: Rediseño del Panel Derecho (ControlPanel)

## Problema
El panel derecho actual tiene controles que no funcionan (Window/Level, presets) e información poco útil. Solo el toggle 2D/3D sirve.

## Propuesta: Reemplazar con controles funcionales inspirados en OHIF/3D Slicer

### Nuevo diseño del panel derecho:

```
┌─────────────────────────┐
│  Controles del Visor    │
├─────────────────────────┤
│ Vista:  [2D] [3D]       │  ← Mantener (funciona)
├─────────────────────────┤
│ Navegación de Corte     │
│ ◀ ━━━━━━━━━━━━━━━━━ ▶  │  ← Slider interactivo
│    Corte 45 / 120       │
├─────────────────────────┤
│ Brillo y Contraste      │
│ ☀ ━━━━━━━━━━━━━━━━━ 50% │  ← CSS filter brightness
│ ◐ ━━━━━━━━━━━━━━━━━ 50% │  ← CSS filter contrast
│ [Cerebro][FLAIR][T2]    │  ← Presets funcionales
│ [Restablecer]           │
├─────────────────────────┤
│ Zoom                    │
│ [−]  125%  [+] [Ajustar]│  ← Botones + % + fit
├─────────────────────────┤
│ Posición del Cursor     │
│ X: 128  Y: 95  Z: 45   │  ← Coordenadas en vivo
│ Intensidad: 1247        │  ← Valor del pixel
├─────────────────────────┤
│ ▶ Información de Imagen │  ← Colapsable
│   256×256 · 120 cortes  │
│   MR · NIfTI            │
│   0.50 × 0.50 mm       │
└─────────────────────────┘
```

## Cambios por archivo

### 1. `store/useViewerStore.ts` — Agregar estado nuevo
- `brightness: number` (0-200, default 100) — CSS brightness %
- `contrast: number` (0-200, default 100) — CSS contrast %
- `cursorInfo: { x, y, z, intensity } | null` — posición del cursor
- Acciones: `setBrightness`, `setContrast`, `setCursorInfo`, `resetImageAdjustments`
- Presets: `applyPreset(name)` que setea brightness + contrast

### 2. `components/ControlPanel.tsx` — Reescribir completo
Reemplazar con secciones funcionales:

**a) Vista 2D/3D** — Mantener tal cual (funciona)

**b) Navegador de corte** — Slider conectado a `currentSliceIndex` / `setCurrentSliceIndex` del store. Muestra "Corte X / Total".

**c) Brillo/Contraste** — Dos sliders (0-200%) que setean `brightness`/`contrast` en el store. Presets: Brain (brightness:100, contrast:150), FLAIR (brightness:120, contrast:130), T2 (brightness:110, contrast:120). Botón "Reset" que vuelve a 100/100.

**d) Zoom** — Botones [-] [+] que llaman `setZoomLevel(current ± 0.25)`. Display del porcentaje. Botón "Ajustar" que hace fit-to-window (zoom=1, pan=0,0).

**e) Posición del cursor** — Lee `cursorInfo` del store, muestra coordenadas X/Y/Z e intensidad.

**f) Info de imagen** — Sección colapsable con formato, dimensiones, cortes, modalidad, spacing. Compacta.

### 3. `components/ImageViewer2D.tsx` — Conectar nuevos controles
- Leer `brightness` y `contrast` del store
- Aplicar `style={{ filter: 'brightness(${b/100}) contrast(${c/100})' }}` al canvas
- En `onMouseMove`: calcular coordenadas + leer pixel del canvas, llamar `setCursorInfo()`
- El slice index ya funciona (lee del store)

### 4. i18n — Agregar claves nuevas
- `viewer.sliceNavigation`, `viewer.sliceOf` ("Corte {{current}} / {{total}}")
- `viewer.brightnessContrast`, `viewer.brightness`, `viewer.contrast`
- `viewer.zoomControls`, `viewer.fitToWindow`
- `viewer.cursorPosition`, `viewer.intensity`
- `viewer.resetAdjustments`
- Agregar en en.json, es.json, de.json

## Lo que se elimina
- Inputs numéricos de Window Center / Window Width (no funcionan, confusos)
- Botón "Aplicar" separado
- Sección de orientación 3D (poco usada, se puede mover si se necesita)
- Emojis en los presets (🧠🔬💧)

## Lo que se mantiene
- Toggle 2D/3D (funciona y es útil)
- Info de imagen (rediseñada y colapsable)
- Presets de contraste (ahora funcionales)

## Notas técnicas
- **Brightness/Contrast via CSS filter**: No modifica los pixels reales, es instantáneo y reversible. Es el approach estándar en web viewers (OHIF lo hace así).
- **Cursor info**: Leyendo del canvas con `getImageData()` en el mouseMove handler que ya existe.
- **Slice slider**: Ya existe `currentSliceIndex` y `setCurrentSliceIndex` en el store, solo falta el UI.
- **Zoom buttons**: Ya existe `zoomLevel` y `setZoomLevel` en el store.
