# Lista de comprobación para el envío — Artículo A → MELBA

**Revista:** Machine Learning for Biomedical Imaging (MELBA), artículo completo.
**Plantilla:** clase LaTeX oficial `melba.cls` v2.03, descargada del repositorio oficial
`github.com/melba-journal/submission` (commit `44b4072`), en modo «envío» (números de línea, sin datos de
número/volumen), sin modificar la clase.
**PDF:** `latex/main.pdf` — **43 páginas**. **Word:** no (MELBA solo acepta LaTeX con su plantilla).
**Fuente del texto:** `manuscript.md` versión 2.0 (revisión mayor, commit `2e9a615`); se reconstruye con
`python latex/build_latex.py`.
**Comprobaciones hechas (4-11-2026):** `tools/check_numbers.py` → 219 de 219 PASS; `latex/TEXT_CHECK.md` →
el texto del PDF es palabra por palabra el de `manuscript.md` (solo cambian los títulos que pone la plantilla:
«Abstract», «Keywords», etiquetas de las declaraciones); 0 citas o referencias sin resolver, 0 cajas que se
salen del margen, 0 caracteres perdidos, 0 tablas o figuras que no caben.

Normas consultadas: página «for authors» de MELBA (melba.scholasticahq.com/for-authors) y README del
repositorio oficial (plantilla de carta, instrucciones de LaTeX), leídos el 31-10-2026.

## 1. Requisitos de la revista

| Requisito de MELBA | Estado | Qué falta / cómo se arregla |
|---|---|---|
| Enviar en LaTeX con la plantilla oficial (otra plantilla = rechazo directo) | **Cumple** | `latex/main.tex` + `melba.cls` sin tocar. |
| Modo de envío: números de línea, sin número/volumen; no modificar la clase | **Cumple** | Los datos del editor (`\melbaid`, `\doi`, volumen, fechas) quedan con los marcadores de la plantilla; se rellenan solo si se acepta. |
| Bibliografía con el estilo de la plantilla (natbib, autor-año, `plainnat`) | **Cumple** | 56 referencias. Arreglo hecho: la clase usa `\doi` para el DOI del artículo y borraba los DOI de todas las referencias; se redefine solo dentro de la bibliografía. 4 avisos menores de BibTeX (registros de datos sin autor se ordenan por clave). |
| Longitud «aproximadamente 20 páginas» (no hay límite estricto) | **No cumple (43 p.)** | Las tablas del apéndice A4–A14 y las tablas largas 4b, 11 y A10 suman muchas páginas. Opciones del autor: pasar el apéndice A a material suplementario, o acortar. No se ha tocado el texto. |
| Resumen (MELBA no fija límite) | **Revisar** | 538 palabras: no cabe con el título en la primera página a dos columnas; se usó la alternativa que da la propia plantilla (`\maketitle` y luego `\twocolumn`). Si se sube a arXiv, el campo de resumen admite como máximo 1.920 caracteres (el actual tiene unos 3.400): hará falta una versión corta para arXiv. |
| Palabras clave | **Cumple** | 10. |
| Secciones finales: Ethical Standards, Conflicts of Interest, Data availability, Acknowledgments | **Cumple (con pendientes)** | Se usan los bloques de la plantilla (`\ethics`, `\coi`, `\data`, `\acks`). «Licences» va dentro de Ethical Standards, «Code availability» dentro de Data availability, «Funding» dentro de Acknowledgments; «Author contributions (CRediT)» y «Use of AI assistance» van como bloques propios con el mismo estilo. Quedan TODO del dueño dentro de esos textos (ver §3). |
| Conflictos de interés declarados en el artículo **y** en la carta | **Cumple (a confirmar)** | Texto del artículo: desarrolla MSTool-AI, afiliado a Daita AI; el autor debe completar «rol comercial, financiación o patentes». La carta repite lo mismo. |
| **Política de IA de MELBA:** se permite usar modelos de lenguaje para pulir el texto o hacer viñetas iniciales, **no para crear contenido nuevo sin supervisión** | **Riesgo alto — no cumple tal como está** | El propio artículo declara que el código, los documentos y **el borrador del manuscrito** los produjo un agente de IA. Antes de enviar: el autor debe revisar y reescribir el texto con sus palabras y declararlo con verdad en la carta; o preguntar antes al editor si este uso es aceptable. |
| Carta de presentación (PDF o texto) con las declaraciones del modelo de MELBA | **Borrador listo** | `latex/cover_letter.md`; faltan fecha, firma, coautores y las confirmaciones marcadas `[DUEÑO: …]`. |
| Todos los autores dados de alta en Scholastica; cambios de autoría solo excepcionales | **Pendiente** | Decidir coautores (estadístico y neurorradiólogo recomendados por el propio texto) **antes** de enviar. |
| Trabajo original, no en revisión en otra revista | **Confirmar** | Hay manuscritos hermanos del mismo programa (negativos, F); se mencionan en la carta. |
| Figuras: derechos sobre las imágenes | **Cumple** | Figuras propias. Van en vectorial (PDF, fuentes incrustadas) a su tamaño de impresión: 180 mm en un ancho de texto de 190 mm, sin escalar. |
| Orden de numeración de figuras y tablas (no lo exige MELBA, es lo habitual) | **Recomendado** | La Figura 7 se cita antes que la 3, y la Tabla 3 antes que la 1. Renumerar exige cambiar el texto: lo decide el autor. |
| Licencia CC-BY 4.0 | **Cumple** | La plantilla la imprime en la portada. |
| Imagen representativa (resumen gráfico) | Solo si se acepta | — |
| Coste | **Sin cargo de publicación** según la comprobación del 17-10-2026 | Confirmar en la web si existe alguna tasa de envío. |

## 2. Cambios de formato hechos al pasar a la plantilla (sin tocar el texto)

- Título, autor, afiliaciones y correo van en los campos de la plantilla (no en el texto).
- Los números de sección escritos a mano se quitaron y LaTeX numera igual (se comprobó número a número).
- Las tablas y figuras conservan su número escrito («Table 4b», «Table A10»), aunque no vayan en orden.
- Tres tablas más altas que una página (11, 4b, A10) van en páginas de una columna y continúan en la página
  siguiente; el resto, a lo ancho de la página.
- El **Apéndice D («Open items before submission (owner checklist)») se mantiene** porque el texto lo cita
  tres veces; es una lista interna y hay que quitarlo, junto con esas tres menciones, antes de enviar.

## 3. Lo que el dueño todavía tiene que hacer

1. **ORCID** (falta; la plantilla tiene el sitio preparado: `\orcid{…}` junto al nombre).
2. **Coautores** y sus aportaciones (CRediT); el texto recomienda un estadístico y un neurorradiólogo.
3. Resolver los 8 TODO del texto (licencia del código y DOI del archivo, ética, financiación, conflictos,
   agradecimientos) y **borrar el Apéndice D** con sus tres menciones.
4. **Política de IA:** revisar y reescribir el texto él mismo (ver la fila de la tabla).
5. Revisar y firmar `cover_letter.md`; dar de alta a todos los autores en Scholastica.
6. Decidir si se recorta a unas 20 páginas (apéndice a material suplementario).

(Ya resuelto en esta revisión: el primer autor de MSLesSeg es Guarnera F.)
