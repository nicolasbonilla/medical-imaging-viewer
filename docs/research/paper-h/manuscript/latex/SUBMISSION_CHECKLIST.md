# Lista de comprobación para el envío — Artículo H → Empirical Software Engineering

**Revista:** Empirical Software Engineering (Springer), artículo de investigación; revisión «single-blind».
**Plantilla:** plantilla oficial de Springer Nature `sn-jnl.cls` v3.1 (diciembre de 2024), descargada de
springernature.com (paquete «Springer Nature LaTeX template»), con el estilo de referencias «Basic
Springer» autor-año (`sn-basic.bst`), como pide la revista, y números de línea. Carpeta plana (sin
subcarpetas), como exige Springer.
**PDF:** `latex/main.pdf` — **36 páginas**. **Word:** `latex/main.docx` (la revista acepta Word o LaTeX;
referencias con el estilo oficial «Springer Basic (author-date)» del repositorio CSL).
**Fuente del texto:** `manuscript.md` v1.0 con los datos de autor del dueño y las figuras rediseñadas v2
(commits `84f4030`, `225422b`); se reconstruye con `python latex/build_latex.py`.
**Comprobaciones hechas (4-11-2026):** `research/paper_h/numbers_check.py` → 73 de 73 cifras OK, 0
problemas; `latex/TEXT_CHECK.md` → mismo texto que `manuscript.md` palabra por palabra; 0 citas o
referencias sin resolver, 0 cajas que se salen del margen, 0 caracteres perdidos, 0 errores. Las citas
textuales de los registros (incluidas las líneas de aprobación con «N. G. Bonilla Vargas») están intactas.

Normas consultadas: «Submission guidelines» de Empirical Software Engineering en link.springer.com
(journal 10664), leídas el 31-10-2026.

## 1. Requisitos de la revista

| Requisito | Estado | Qué falta / cómo se arregla |
|---|---|---|
| Word o LaTeX; plantilla LaTeX de Springer Nature; fuentes editables con cada envío; sin subcarpetas | **Cumple** | `latex/` contiene `main.tex`, la clase, el `.bst`, el `.bib`, las figuras y el `main.bbl`, todo en la misma carpeta (la subcarpeta `template/` es solo de referencia y no se sube). |
| Resumen de **150 a 250 palabras**; estructurado permitido (Context, Objective, Method, Results, Conclusions) | **No cumple** | Estructura correcta, pero tiene **628 palabras**. Hay que dejarlo en 250 como máximo: decisión del autor (no se toca el texto). |
| **De 4 a 6 palabras clave** | **No cumple** | Tiene 12. Propuesta: AI coding agents; IEC 62304; medical device software; mutation testing; regulatory compliance; case study. |
| Página de título: nombres, afiliaciones (institución, ciudad, país), correo del autor de correspondencia, ORCID si lo hay | **Cumple salvo ORCID** | Universidad Nacional de Colombia (Bogotá, Colombia); SRH University München (Múnich, Alemania); Daita AI; ngbonillav@unal.edu.co. Falta el ORCID. |
| Referencias autor-año («Thompson 1990»), DOI como enlace completo, orden alfabético | **Cumple** | 69 referencias con `sn-basic`. |
| Declaraciones obligatorias: Funding, Competing interests, Ethics approval and consent to participate, Consent for publication, Data availability, Materials availability, Code availability, Author contribution | **Cumple (con pendientes)** | Añadidas las que faltaban (ética y consentimiento, consentimiento de publicación, materiales: «Not applicable»), sacadas de lo que ya dice la Sección 8. «Data and code availability» va junto (Springer las lista por separado: separarlas es opcional). Quedan confirmaciones del dueño (financiación, conflictos). Sin declaraciones completas, Springer devuelve el envío. |
| Conflictos de interés completos | **Cumple (a confirmar)** | Dueño del producto estudiado, afiliación a Daita AI, cliente de Anthropic (proveedor del agente estudiado); lo no verificable va marcado «owner to confirm». |
| **Uso de modelos de lenguaje documentado en Métodos** | **Cumple en parte** | La Sección 4.5 dice que el agente codificó los datos como único codificador; que el agente escribió los scripts y el borrador solo está en las Declaraciones. Recomendado: una frase en la Sección 4 (decisión del autor). El simple pulido de texto no hace falta declararlo. |
| Figuras: citadas en **orden numérico consecutivo** | **No cumple** | El texto cita la Figura 7 antes que la 2 y la 8 antes que la 6 (orden 1, 7, 2, 8, 6, 3, 4, 5). Arreglo: renumerar figuras y menciones (cambia el texto: lo decide el autor). |
| Figuras: vectoriales con fuentes incrustadas; ancho máximo 174 mm; pie «Fig. N» | **Cumple** | PDF vectoriales a 174 mm (la Figura 7, 129 mm), sin escalar; como la plantilla de envío tiene 131 mm de texto, las figuras anchas sobresalen centradas en el margen (tamaño final de la revista). Springer prefiere EPS pero acepta PDF desde LaTeX; nombres de archivo «Fig1…» recomendados (renombrar al subir). |
| Tablas con número y título | **Cumple** | 4 tablas. |
| Encabezados numerados con un máximo de tres niveles | **Cumple** | El nivel más profundo es el tercero («5.2.1»). |
| Revisión single-blind (los nombres pueden ir en el manuscrito) | **Cumple** | — |
| Carta de presentación | **Borrador listo** | `latex/cover_letter.md`. |
| Coste | **Sin cargo** salvo que se elija acceso abierto | Revista por suscripción con opción de acceso abierto de pago. |

## 2. Cambios de formato hechos al pasar a la plantilla (sin tocar el texto)

- Título, autor, afiliaciones, correo, resumen y palabras clave van en los campos de la plantilla; las líneas
  «Author» y «Corresponding author» del Markdown se sustituyen por esa cabecera.
- Las figuras se numeran como en el texto (por su número de archivo), no por orden de aparición, para que
  todas las menciones «Figure N» sigan siendo correctas.
- Los números de sección se quitaron y LaTeX numera igual; donde el texto empieza en «5.0» se fuerza ese
  número (comprobado).
- Las declaraciones van tras `\backmatter`, como en la plantilla de Springer.

## 3. Lo que el dueño todavía tiene que hacer

1. **ORCID** (16 dígitos) y, si hay, **coautores**.
2. **Recortar el resumen a 250 palabras** y **dejar 4–6 palabras clave**.
3. Decidir si renumera las figuras por orden de cita.
4. Resolver los puntos de `OWNER_REVIEW.md` y las 23 marcas pendientes del texto (A1 ORCID, A2
   financiación y conflictos, A3 declaración de IA, A4 ética, B3–B4 búsqueda y archivo con DOI, C4–C6
   comprobaciones de seguridad).
5. Revisar y firmar `cover_letter.md`.
