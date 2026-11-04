# Lista de comprobación para el envío — Artículo de resultados negativos → MELBA

**Revista:** Machine Learning for Biomedical Imaging (MELBA), artículo completo.
**Plantilla:** clase LaTeX oficial `melba.cls` v2.03, descargada del repositorio oficial
`github.com/melba-journal/submission` (commit `44b4072`), en modo «envío» (números de línea), sin
modificar la clase.
**PDF:** `latex/main.pdf` — **19 páginas**. **Word:** no (MELBA solo acepta LaTeX con su plantilla).
**Fuente del texto:** `manuscript.md` (borrador v0.2 con los datos de autor del dueño y las figuras
rediseñadas v2); se reconstruye con `python latex/build_latex.py`.
**Comprobaciones hechas (4-11-2026):** `scripts/check_numbers.py` → 120 de 120 PASS; `latex/TEXT_CHECK.md` →
mismo texto que `manuscript.md` palabra por palabra (diferencias solo de estructura, ver §2); 0 citas o
referencias sin resolver, 0 cajas que se salen del margen, 0 caracteres perdidos, 0 errores.

Normas consultadas: página «for authors» de MELBA (melba.scholasticahq.com/for-authors) y README del
repositorio oficial, leídos el 31-10-2026.

## 1. Requisitos de la revista

| Requisito de MELBA | Estado | Qué falta / cómo se arregla |
|---|---|---|
| Enviar en LaTeX con la plantilla oficial (otra plantilla = rechazo directo) | **Cumple** | `latex/main.tex` + `melba.cls` sin tocar. |
| Modo de envío: números de línea, sin número/volumen | **Cumple** | Datos del editor con los marcadores de la plantilla. |
| Bibliografía con el estilo de la plantilla (`plainnat`, autor-año) | **Cumple, con aviso** | 36 referencias con DOI. **8 referencias imprimen notas internas «CHECK ONLINE: …»** que vienen del campo `note` de `references.bib` (referencias aún sin comprobar en línea). Hay que comprobarlas y borrar esas notas antes de enviar. |
| Longitud «aproximadamente 20 páginas» | **Cumple** | 19 páginas. |
| Resumen (MELBA no fija límite) | **Revisar** | 566 palabras, resumen estructurado: no cabe con el título en la primera página a dos columnas; se usó la alternativa de la propia plantilla (`\maketitle` y luego `\twocolumn`). Para arXiv el resumen admite como máximo 1.920 caracteres (el actual tiene unos 3.700): hará falta una versión corta. |
| Palabras clave | **Cumple** | 13 (MELBA no fija número). |
| Secciones finales: Ethical Standards, Conflicts of Interest, Data availability, Acknowledgments | **Cumple (con pendientes)** | Bloques de la plantilla. «Licences of data and tools» va en Ethical Standards, «Code availability» en Data availability, «Funding» en Acknowledgments; «Use of AI assistance» y «Author contributions (CRediT)» como bloques propios. Quedan TODO del dueño (ver §3). |
| Conflictos de interés en el artículo **y** en la carta | **Cumple (a confirmar)** | Actualizado: MSTool-AI (con intención comercial), afiliación a Daita AI, uso de un agente comercial (Anthropic); lo que no se puede verificar va marcado «owner to confirm». |
| **Política de IA de MELBA:** modelos de lenguaje solo para pulir el texto o hacer viñetas iniciales, **no para crear contenido nuevo sin supervisión** | **Riesgo alto — no cumple tal como está** | El artículo declara que el agente redactó el manuscrito. El autor debe revisar y reescribir el texto él mismo y declararlo con verdad en la carta, o consultar antes al editor. |
| Carta de presentación con las declaraciones del modelo de MELBA | **Borrador listo** | `latex/cover_letter.md`. |
| Autores dados de alta en Scholastica | **Pendiente** | Decidir coautores antes de enviar. |
| Trabajo original, no en revisión en otra revista | **Confirmar** | Manuscritos hermanos del mismo programa mencionados en la carta. |
| Figuras: derechos; calidad | **Cumple** | Figuras propias, vectoriales (PDF con fuentes incrustadas), a su tamaño de impresión (180 mm; la Figura 5, 130 mm), sin escalar. |
| Orden de numeración de figuras (no lo exige MELBA) | **Recomendado** | La Figura 3 y la 6 se citan antes que la 1. Renumerar cambia el texto: lo decide el autor. |
| Licencia CC-BY 4.0 | **Cumple** | En la portada. |
| Coste | **Sin cargo de publicación** según la comprobación del 17-10-2026 | La nota interna mencionaba una pequeña tasa de envío: confirmarlo en la web. |

## 2. Cambios de formato hechos al pasar a la plantilla (sin tocar el texto)

- Título, autor, afiliaciones y correo van en los campos de la plantilla.
- La nota interna «Submission note (internal; delete before submission)» no se incluye (lo pide ella misma).
- La sección «Figure legends» del final se convirtió en los pies de las figuras, y cada figura se colocó
  después del primer párrafo que la cita (MELBA quiere las figuras en el texto). La frase general sobre la
  paleta de colores quedó al final del pie de la Figura 1.
- Los números de sección se quitaron y LaTeX numera igual (comprobado).
- Tablas a lo ancho de la página cuando no caben en una columna.

## 3. Lo que el dueño todavía tiene que hacer

1. **ORCID** (falta; la plantilla tiene el sitio preparado junto al nombre).
2. **Coautores**, si los hay, y sus aportaciones (CRediT).
3. Resolver los TODO del texto (17 marcas): repositorio público en las fechas de la Tabla 1, licencia del
   código, DOI del archivo en Zenodo, publicación o no de los pesos ajustados, ética, financiación,
   conflictos (rol en Daita AI, participación, patentes), su propio papel en la revisión del texto.
4. Comprobar las **8 referencias con «CHECK ONLINE»** y borrar esas notas de `references.bib`.
5. **Política de IA:** reescribir/revisar él mismo el texto (ver la fila de la tabla).
6. Revisar y firmar `cover_letter.md`; dar de alta a los autores en Scholastica.
