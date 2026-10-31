# Lo que tiene que confirmar el dueño antes de enviar el artículo H

Texto preparado por el asistente de IA el 31-10-2026. Nada de esto está confirmado. Cada punto tiene un
código (A1, C4…) que el artículo cita entre paréntesis. **No se envía el artículo a ninguna revista
mientras quede un punto de las partes A, B o C sin resolver.**

Cómo usar esta lista: al lado de cada punto escriba "confirmado", "corregir: …" o "quitar del
artículo". El asistente aplica después los cambios, pero las decisiones y las firmas son suyas.

---

## A. Autoría y declaraciones

- **A1 — Sus datos.** Afiliación (¿"MSTool-AI", ciudad, país?), ORCID y dirección de contacto. El
  artículo tiene huecos marcados.
- **A2 — Financiación y conflictos de interés.** Confirme que no hay financiación. Declare cualquier
  relación con la empresa que hace el asistente de IA y con los autores citados (también si alguno
  comparte apellido con usted y no hay relación: conviene decirlo). Esa comprobación no se escribe en
  archivos públicos.
- **A3 — Uso de IA en el artículo.** El borrador lo escribió el mismo asistente que el artículo
  estudia, igual que casi todo el código y los registros. Hay que leer el texto entero, hacerlo suyo
  y ajustar la declaración a las normas de la revista elegida (Springer para *Empirical Software
  Engineering*, Elsevier para *Journal of Systems and Software*, ACM/IEEE para ICSE-SEIP).
- **A4 — Comité de ética.** El artículo dice que no hizo falta porque solo analiza sus propios
  registros de trabajo. Confirme que la revista lo acepta así.
- **A5 — Permiso para publicar.** Confirme que acepta publicar el contenido de los registros, las
  descripciones de las propuestas de cambio y sus notas sobre las dos negativas del sistema de
  permisos (punto C3).

## B. Método

- **B1 — Una segunda persona que clasifique (imprescindible).** Hoy toda la clasificación la hizo el
  asistente solo: los 33 episodios de fallo, los 189 hallazgos de revisión y el canal de los 38
  registros. Hace falta una persona independiente que repita la clasificación y calcule el acuerdo
  (kappa de Cohen). Sin esto, una revista seria lo rechazará.
- **B2 — Que otra persona repita los cálculos.** Los programas están en `research/paper_h/`; alguien
  ajeno debería ejecutarlos y obtener las mismas cifras (`NUMBERS_CHECK.md`).
- **B3 — Repetir la búsqueda de trabajos parecidos** justo antes de enviar. El campo cambia cada
  semana; la última comprobación de las referencias es del 31-10-2026.
- **B4 — Archivo permanente.** Congelar la versión y guardarla con identificador permanente (por
  ejemplo, Zenodo) antes de enviar.
- **B5 — Revista y extensión.** Elegir entre *Empirical Software Engineering* (artículo largo, el
  recomendado), *Journal of Systems and Software*, o una versión corta de 10 páginas para ICSE-SEIP
  2027 (habría que recortar mucho).

## C. Datos de incidentes que solo usted puede confirmar

- **C1 — Quién hizo el guardado del 23-10-2026 que registró sus aprobaciones (`8832dae`).** No lleva
  la marca del asistente, no está firmado y se hizo en el ordenador, no en la web de GitHub. El
  artículo dice que su origen no está demostrado. Diga si lo hizo usted mismo o si lo hizo el
  asistente por orden suya. **Si lo hizo el asistente, el artículo debe decirlo**: sería otra
  aprobación escrita por el asistente, hecha después de abrir la acción correctiva CAPA-012 que lo
  prohíbe.
  **Y las tres firmas del 30 y 31-10-2026** (`5561999`, `c1d0e04`, `042d50b`): GitHub las marca como
  verificadas, pero esa marca solo demuestra que se hicieron a través de GitHub con su cuenta, no que
  las hiciera su mano; el asistente tiene acceso a su cuenta de GitHub en este ordenador. Confirme por
  escrito que las hizo usted mismo en el navegador. El artículo lo dice así, con esta salvedad.
- **C2 — Las 62 cuentas de prueba en la base de usuarios de producción (PRB-002).** ¿Se borraron?
  Confirme las cifras (62 cuentas, 112 escrituras) y que esas cuentas no permiten entrar en
  producción.
- **C3 — El sistema de permisos del asistente.** El artículo cuenta, según sus notas, dos negativas
  (entre el 17 y el 21-10-2026) a escribir su aprobación en los documentos. Confirme fechas y
  contenido. **Si también hubo negativas a actuar sobre producción** (publicar, borrar datos,
  órdenes a la nube), el artículo solo puede contarlo si usted lo confirma y aporta pruebas sin datos
  personales (por ejemplo, el texto de la negativa). Hoy el artículo dice que eso no consta en el
  repositorio.
- **C4 — Registro abierto y lista de pacientes visible (PRB-020 y PRB-021).** Antes de publicar hay
  que confirmar: (a) que el arreglo está publicado en producción; (b) si en producción había datos de
  pacientes reales o solo datos de demostración o de investigación; (c) si existían cuentas creadas
  por desconocidos y qué se hizo con ellas; (d) el resultado de revisar los accesos a la lista de
  pacientes y si hizo falta la evaluación de protección de datos (artículo 33 del RGPD). El artículo
  dice hoy "se desconoce si se leyeron datos".
- **C5 — Qué está publicado en producción.** Las cifras de "días hasta la copia principal" no dicen
  nada de producción. Confirme qué arreglos (propuestas de cambio 64, 70, 72 y 74) están ya en el
  servicio que usan los usuarios.
- **C6 — La contraseña de administrador que estuvo escrita en el repositorio** (eliminada el
  10-07-2026, guardado `fd2aa2e`; el repositorio es público y la contraseña sigue en el historial).
  **Confirme que se cambió.** Si no se cambió, hay que cambiarla antes de nada y quitar el párrafo
  del artículo hasta entonces.
- **C7 — El envío a otro proyecto de la nube (propuesta de cambio 44).** El artículo lo cuenta de
  forma anónima ("un producto suyo sin relación") y sin decir quién lanzó la orden, porque el
  repositorio no lo dice. Confirme si fue el asistente (sus notas así lo indican) y si acepta esta
  redacción. Confirme también que no se tocó ningún dato de ese otro producto. No se nombra ese
  producto en ningún archivo del artículo.
- **C8 — Contraseñas en los registros del servidor.** ¿Se revisaron los registros de producción en
  busca de contraseñas escritas por el error que se corrigió en la propuesta de cambio 70? ¿Se
  borraron?
- **C9 — Su papel en encontrar fallos.** Los registros no atribuyen ningún hallazgo a usted. Si usted
  encontró o señaló fallos (por ejemplo, los "dos defectos comunicados al asistente" que abrieron
  CAPA-015), dígalo: el artículo lo corregirá.
- **C10 — Estado del producto.** Confirme las frases "no tiene marcado CE, no está aprobado por la
  FDA, no se usa en clínica, se usa para evaluación".

## D. Registros que han quedado mal y que este artículo ha descubierto

Estos defectos están en los documentos regulados de la copia principal. **El asistente no los ha
tocado en esta rama**: corregirlos es un cambio controlado que usted debe decidir (posiblemente una
nueva acción correctiva, CAPA-017).

- **D1 — El plan de desarrollo dice ahora lo contrario de lo que quería decir.** La sustitución
  automática del 23-10-2026 cambió "el asistente escribe `PENDING owner approval`" por "el asistente
  escribe `approved by N. G. Bonilla Vargas …`" en SDP-001 §4.4 y §7.4, y lo mismo en CAPA-012
  (PA-12.1 y PA-12.2). Tal como está, el procedimiento aprobado ordena al asistente escribir su
  aprobación.
- **D2 — PRB-020 dice "aprobado … y revisión de código"**, porque la sustitución cambió "PENDING
  owner approval and code review". No hubo revisión de código humana.
- **D3 — Documentos de otro cambio quedaron como aprobados.** La firma de la propuesta de cambio 70
  marcó como aprobados cuatro documentos del cálculo en el navegador (CP-FLAMES-BROWSER-001), que no
  formaban parte de esa propuesta. Uno dice a la vez "NOT approved" y "approved … (PR #70)".
- **D4 — Notas de las entregas que se contradicen** ("todas las casillas siguen diciendo: aprobado").
- **D5 — Estados atrasados.** 25 de los 38 registros dicen que el arreglo está "en una rama" o "sin
  unir", cuando ya está en la copia principal. Ninguna de las 16 acciones correctivas está cerrada.
- **D6 — Controles que siguen sin existir.** La copia principal sigue sin protección (GitHub responde
  "Branch not protected" el 31-10-2026); el asistente sigue usando su identidad; no hay revisor humano
  independiente para los módulos de Clase C (CAPA-012, CA-12.3 y CA-12.5 abiertas).
- **D7 — La propuesta de cambio 74 se unió antes de su firma**; la firma llegó después con la 75.

Propuesta para el futuro (decisión suya): que la firma no sustituya texto libre, sino casillas de
aprobación con un formato fijo, y que una comprobación automática rechace la marca de "pendiente"
fuera de esas casillas.

## E. Cosas del texto que conviene revisar con calma

- **E1** — 88 de los 189 hallazgos de revisión no tienen gravedad en el registro. Decida si se
  presentan así o si la segunda persona (B1) los clasifica.
- **E2** — Los 15 casos de "sustitución que no era una casilla" salen de una regla automática; la
  lista está en `research/paper_h/out/manuscript_data.json`, clave
  `approvals.signoff_substitutions.commits[*].non_placeholder_examples`. Conviene revisarlos a mano.
- **E3** — El título y el mensaje central ("pruebas que pueden fallar"). Si prefiere otro enfoque,
  dígalo antes de la revisión de estilo.
- **E4** — No se pudo producir el documento en Word ni en PDF: el programa de conversión (pandoc) no
  está instalado en este ordenador. Se puede hacer cuando se instale.
