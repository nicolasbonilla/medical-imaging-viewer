# Artículo D — resumen para el dueño (31-10-2026)

## De qué trata, en una frase

Los programas que leen resonancias de esclerosis múltiple dicen si se cumple la **"diseminación en
el espacio"** (lesiones en al menos dos regiones del cerebro, uno de los requisitos para el
diagnóstico). El artículo D mide **cuántas veces esa respuesta cambia** si se cambian decisiones
técnicas igual de razonables (qué programa dibuja las lesiones, qué umbral, qué mapa del cerebro…).

## Qué hemos encontrado hasta ahora (124 estudios públicos, sin radiólogos todavía)

- En **casi 4 de cada 10 estudios (38,7 %)** al menos una de las 1.120 combinaciones razonables da la
  respuesta contraria; en 1 de cada 10 las combinaciones están muy divididas.
- En los estudios con **pocas lesiones** — justo donde la decisión importa — pasa en **2 de cada 3**.
- Lo que más cambia la respuesta es **qué programa dibuja las lesiones**, no los ajustes finos.
- La región del **tronco y cerebelo** (infratentorial) es la menos fiable.
- La configuración automática por defecto de la aplicación coincide con la referencia en el 96,8 % de
  los estudios (difiere en 4 de 124).

Todo esto compara con una referencia hecha **por el propio programa sobre las lesiones dibujadas por
un experto**. Para que el artículo sea sólido falta lo esencial: **lo que dicen tres neurorradiólogos.**

## Qué está listo (todo guardado en GitHub, propuesta de cambios n.º 61, sin unir a la copia principal)

| Archivo | Qué es |
|---|---|
| `manuscript/manuscript.md` | El artículo completo en borrador con todos los resultados actuales; lo que necesita a los radiólogos está marcado "TODO". 27 referencias comprobadas una a una. |
| `READER_STUDY_PROTOCOL.md` | El plan del estudio con los tres neurorradiólogos: qué casos (84), cómo se leen, cómo se evita que se influyan, cuánto tiempo (unas 8 horas cada uno), ética, autoría. |
| `INVITATION_EMAIL.md` | El correo de invitación, listo para enviar, en inglés y en alemán. |
| `APP_FEATURE_SPEC.md` | Cómo se convierte en función de la aplicación y qué hay que validar antes. |
| `research/paper_d/select_reader_cases.py`, `reader_power.py` | La elección de los 84 casos (siempre la misma, con semilla fija) y el cálculo de cuántos casos hacen falta. |

Dato importante: **el repositorio de GitHub es público**. Por eso la lista que dice qué caso es
"difícil" y cuál no **no se ha subido**: está solo en tu ordenador, en la carpeta de datos. Si un
lector la viera, el estudio dejaría de ser ciego.

## Lista de pasos para ti (lo único que tienes que hacer)

1. **Elige tres neurorradiólogos** (y apunta dos de reserva). Que tengan experiencia en esclerosis
   múltiple, idealmente de **hospitales distintos**, que **no trabajen para ti ni tengan intereses en
   MSTool-AI**, y que puedan dedicar unas **8 horas en 8 semanas**.
2. **Envía el correo de `INVITATION_EMAIL.md`**, uno a cada persona por separado (no en copia a los
   tres: no deben saber quiénes son los otros hasta el final). Inglés o alemán según la persona.
   Rellena solo lo que está entre corchetes: nombre, fecha límite de respuesta (unas 2 semanas),
   tu correo profesional y tu teléfono.
3. **Cuando alguien acepte, avísame.** Si alguien dice que no, invita a una persona de reserva.
4. **No les cuentes nada más** sobre los resultados ni sobre qué casos son difíciles, y no les
   reenvíes la lista de casos.

Eso es todo. Según nuestra lectura del código profesional de los médicos en Alemania, con datos
públicos y anónimos no hace falta un permiso formal de un comité de ética; y si el hospital de algún
lector pide un informe, ese trámite le corresponde al médico que participa: le daremos la carta ya
escrita en alemán (apéndice B del protocolo).

## Lo que hago yo cuando acepten (no necesitas hacer nada)

1. Construir el **programa de lectura** a partir del visor de MSTool-AI: un único archivo que se abre
   en Chrome o Edge, sin instalar nada y **sin conexión** (unos 2–3 días), y comprobarlo con las seis
   pruebas del protocolo, incluida la de izquierda/derecha.
2. Preparar los paquetes de casos (con el aviso de autoría de los datos), el consentimiento, y la
   carta para el comité de ética por si el hospital de algún lector la pide.
3. Registrar el protocolo en OSF con fecha **antes** de la primera lectura.
4. Organizar las tres sesiones (primera lectura; un mes de pausa; clasificación de lesiones y 12
   relecturas), recoger los archivos de respuestas, analizar y rellenar el artículo.
5. Enviar el borrador a los lectores para que lo revisen y aprueben (así cumplen los requisitos para
   ser coautores).

## Lo que conviene saber con honestidad

- **Tiempo que pedimos:** unas 8 horas por lector (entre 6 y 10). Si en los casos de prueba se ve que
  serían más de 10, el protocolo ya prevé recortar la clasificación de lesiones.
- **No hay pago**; se ofrece **ser coautor** si además revisan y aprueban el artículo.
- **Probabilidad de que el estudio muestre lo principal** (que los casos "difíciles" para los programas
  también lo son para los expertos): alrededor del **77 %** si la diferencia real es grande (25 % de
  desacuerdo frente a 5 %); menor si es más pequeña. No se pueden añadir más casos difíciles: no
  existen más en estos datos.
- Los estudios son de personas con esclerosis múltiple ya establecida; en pacientes en fase temprana
  la fragilidad será probablemente mayor, pero eso será otro estudio.

## Cómo llega a la aplicación (confirmado)

Función: **"aviso de estabilidad de la diseminación en el espacio"**. La aplicación calcularía la
respuesta también con un **segundo programa de segmentación**; si no coinciden, o si la respuesta
depende de una o dos lesiones, mostraría **"Frágil — revisar"** y señalaría las lesiones que marcan
la diferencia, para que el radiólogo las confirme. **No se puede construir todavía**: (1) la señal se
descubrió con estos mismos datos y hay que confirmarla con los tres neurorradiólogos y después con
pacientes en fase temprana; (2) el segundo programa necesita una licencia que permita venderlo
(FLAMeS no la tiene; LST-AI se declara solo para investigación); (3) después, el proceso de seguridad
de la aplicación (requisito, análisis de riesgos, revisión, pruebas y tu aprobación).
