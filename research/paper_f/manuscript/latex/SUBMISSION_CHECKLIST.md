# Lista de comprobación para el envío — Artículo F → NeuroImage: Clinical

**Revista:** NeuroImage: Clinical (Elsevier), artículo de investigación; acceso abierto completo.
**Plantilla:** clase oficial de Elsevier `elsarticle.cls` v3.5 (2026-01-09), generada desde el paquete de
CTAN (`elsarticle.dtx`), con referencias autor-año (`elsarticle-harv.bst`), en el formato de doble columna
de la revista (`5p`) para que las figuras de 88/180 mm salgan a su tamaño, y con números de línea.
**PDF:** `latex/main.pdf` — **22 páginas** (la primera es la página de «Highlights» que imprime la clase).
**Word:** `latex/main.docx` (Elsevier acepta Word; referencias con el estilo oficial «Elsevier Harvard» del
repositorio CSL). **Highlights aparte:** `latex/highlights.docx` (Elsevier los pide en un archivo propio).
**Fuente del texto:** `manuscript.md` v1.1 (revisión mayor, commits `41ad117` y `4502940`, figuras v2
`395d2fd`); se reconstruye con `python latex/build_latex.py`.
**Comprobaciones hechas (4-11-2026):** `numbers_check.py` → 480 de 480 PASS; `latex/TEXT_CHECK.md` → mismo
texto que `manuscript.md` palabra por palabra; 0 citas o referencias sin resolver, 0 cajas que se salen del
margen, 0 caracteres perdidos, 0 errores.

Normas consultadas el 31-10-2026: guía para autores de NeuroImage: Clinical en ScienceDirect (la página
devuelve «403» a las consultas automáticas, así que sus cifras se tomaron de los extractos de búsqueda
— **conviene confirmarlas en la página viva**), y la política de Elsevier sobre IA generativa
(elsevier.com, «The use of generative AI and AI-assisted technologies in writing for Elsevier»,
actualizada en julio de 2026).

## 1. Requisitos de la revista

| Requisito | Estado | Qué falta / cómo se arregla |
|---|---|---|
| Formato libre en el primer envío («Your Paper Your Way»); LaTeX con `elsarticle` o Word | **Cumple** | PDF desde `elsarticle` y versión Word. |
| Resumen de **250 palabras como máximo** | **No cumple** | 298 palabras con los rótulos (294 sin ellos). Hay que recortar unas 50 palabras: decisión del autor (no se toca el texto). |
| **De 1 a 7 palabras clave** | **No cumple** | Tiene 12. Propuesta: multiple sclerosis; lesion segmentation; FLAIR; slice thickness; benchmark; pre-registration; nnU-Net (los nombres de las herramientas ya están en el título y el resumen). |
| Highlights: de 3 a 5 viñetas, **85 caracteres como máximo** cada una, en archivo aparte | **Cumple** | 5 viñetas de 73–82 caracteres; `highlights.docx`. |
| Referencias: cualquier estilo coherente | **Cumple** | Autor-año (Harvard), 46 referencias con DOI. |
| Declaración de intereses en conflicto | **Cumple (a confirmar)** | En el texto («Conflict of interest»), con TODO del dueño. Además Elsevier pide rellenar su formulario de declaración de intereses al enviar. El título recomendado por Elsevier es «Declaration of competing interest»: cambio de título opcional. |
| Declaración CRediT | **Cumple (a confirmar)** | Sección «Author contributions (CRediT)»; Elsevier la titula «CRediT authorship contribution statement» (opcional). Faltan coautores. |
| Disponibilidad de datos | **Cumple** | «Data availability», con TODO (depósito de máscaras, licencia y DOI del código). |
| **Declaración de IA generativa** con la redacción de Elsevier, **justo encima de las referencias** | **Cumple (a confirmar)** | Título y frase de Elsevier («During the preparation of this work the author used …»), colocada inmediatamente antes de «References» también en el PDF. La frase de responsabilidad está marcada «Owner to confirm»: solo puede quedar si es verdad. El papel del agente en la investigación está en Métodos 2.1, como pide Elsevier. |
| Ética | **Cumple (a confirmar)** | Datos públicos anonimizados; TODO: confirmar si hace falta una exención formal. |
| Financiación | **Cumple** | «No specific grant…»; crédito gratuito de nube declarado. |
| Página de título: autores, afiliaciones, autor de correspondencia con correo | **Cumple** | En la plantilla: Universidad Nacional de Colombia (Bogotá), SRH University München (Múnich), Daita AI; ngbonillav@unal.edu.co. La frase «The author develops MSTool-AI…» del párrafo de afiliaciones va como nota del autor. |
| Figuras: calidad y tamaño | **Cumple** | Vectoriales (PDF con fuentes incrustadas) a 180 mm, ancho de doble columna de Elsevier (190 mm), sin escalar. Se citan en orden 1–4. |
| Tablas editables (no imágenes) | **Cumple** | Todas son tablas de texto; la Tabla 6, más alta que una página, va en páginas de una columna y continúa. |
| Números de línea para revisores | **Cumple** | Activados. |
| Límite de palabras del texto principal | **Sin confirmar** | No se pudo leer en la guía viva. El texto principal tiene unas 6.700 palabras (sin tablas, resumen ni referencias). |
| Resumen gráfico | Opcional | — |
| Lista de comprobación CLAIM citada en Métodos | **Pendiente** | El propio texto dice «[TODO owner: complete and attach the checklist]». |
| **Cargo de publicación (APC)** | **Coste a decidir** | NeuroImage: Clinical es de acceso abierto completo: **3.490 USD** (sin impuestos) según la página de ScienceDirect; Elsevier aplica precios por país. Comprobar descuentos o exenciones antes de enviar. |

## 2. Cambios de formato hechos al pasar a la plantilla (sin tocar el texto)

- Título, autor, afiliaciones, correo, resumen, highlights y palabras clave van en los campos de la plantilla.
- Las notas internas de la cabecera («Target journal», «Running title») no se imprimen.
- Las declaraciones, el apéndice y la declaración de IA conservan el orden del Markdown, que deja la
  declaración de IA inmediatamente encima de las referencias.
- Los números de sección se quitaron y LaTeX numera igual (comprobado).

## 3. Lo que el dueño todavía tiene que hacer

1. **ORCID** (se añade en el sistema de envío de Elsevier) y **coautores** con sus aportaciones.
2. **Recortar el resumen a 250 palabras** y **dejar 7 palabras clave** como máximo.
3. Resolver los TODO del texto (16 marcas): departamento/ciudad tal como deben figurar, licencia y DOI
   del código, depósito de máscaras, ética, conflictos (rol en Daita AI o SRH), la frase de responsabilidad
   de la declaración de IA, quién lanzó cada ejecución en la nube, la lista CLAIM.
4. Rellenar el formulario de intereses de Elsevier y decidir sobre el **cargo de 3.490 USD**.
5. Revisar y firmar `cover_letter.md`.
6. (Para el coordinador) La línea de autor del YAML de `manuscript.md` todavía dice «[TODO owner: …
   corresponding e-mail]» aunque el correo ya se conoce; el PDF ya lo lleva.
