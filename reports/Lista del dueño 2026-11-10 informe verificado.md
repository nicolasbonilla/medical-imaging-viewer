# Lista del dueño — informe de IA con comprobación automática (10-11-2026)

**Estado:** borrador para su revisión y firma. No se ha unido a la copia principal ni se ha publicado nada.
Propuesta de cambio en GitHub: https://github.com/nicolasbonilla/medical-imaging-viewer/pull/78 (borrador)

## Para firmar — lista final (undécima revisión, la última ronda de correcciones)

Todo lo de abajo está **en borrador**. Yo no he escrito ninguna aprobación a su nombre.

### Lo que cambió en esta última ronda

- Los dos avisos de qué se envía a la IA (el del panel y el del pie del informe) **decían que se envían el sexo y la edad, y no es así**. Ahora dicen exactamente lo que se envía, en los tres idiomas, y una prueba lo compara con los datos reales para que no vuelva a pasar.
- Cuando faltaba uno de los recuentos de la comparación (resueltos, reducidos, estables), **desaparecían los tres**. Ahora salen los que hay y el que falta dice «no calculado».
- Si el control de privacidad confunde una medida con un dato del paciente (por ejemplo 9,1175 ml leído como la fecha de nacimiento 9-11-75), **se entrega el informe de mediciones** con una nota, en lugar de un error sin informe.
- El registro cuenta solo las preguntas que de verdad se enviaron a la IA; si al repetir ya no quedaba tiempo, se anota aparte.
- Si la IA contestó, su texto no pasó la comprobación y al repetir falla el servicio, el informe dice que **el texto no pasó la comprobación** (no «no se pudo obtener»).
- La lista de palabras propias del programa se prepara **al arrancar el servidor**, no durante el primer informe.
- Controles negativos de esta ronda: 12 de 12 detectados; panel 1 de 1.

### Sus decisiones (marque cada una)

1. [ ] **Gravedad de HAZ-017** (el modelo de IA se retira): propuesta moderada (S3); antes del cambio frecuente, después remota.
2. [ ] **Comentarios de la IA al lanzar:** recomiendo **apagados** (`REPORT_LLM_ENABLED=false`, solo medidas) hasta medir Claude Sonnet 5.5 en el estudio.
3. [ ] **Respaldo automático del proveedor:** apagado (si Claude se niega, sale el informe con las medidas).
4. [ ] **Recuento desde 20 lesiones:** el borrador solo dice el rango MAGNIMS 2021; el número exacto queda en el análisis de lesiones.
5. [ ] **Lesiones nuevas pequeñas:** «Además se marcaron {k} lesiones nuevas de menos de {d} mm por debajo del tamaño mínimo de revisión, que no se propusieron como candidatos de cambio.»
6. [ ] **Cantidades con negación** («no hay lesiones grandes»): no rechazarlas.
7. [ ] **Instrucción «no escribas números con letras»:** solo junto con una nueva medición con Claude.
8. [ ] **Aviso de candidatos sin la fecha de la medición** (la fuente sigue citada).
9. [ ] **Medida imposible:** se rechaza (código 422) y el médico ve: «La medida «recuento de lesiones», calculada por el análisis de la segmentación, está fuera de su rango plausible, por lo que no se escribió ningún borrador. Vuelva a ejecutar el análisis o revise la segmentación. No se envió nada al servicio de IA.» (también en inglés y alemán).
10. [ ] **Los 9 mensajes nuevos del panel** para cada error (apartado `report.errors` de los archivos de idioma).
11. [ ] **Coincidencia con un dato del paciente** (un número o un patrón): informe de mediciones con la nota de privacidad, sin preguntar a la IA.
12. [ ] **Orden ficha y tiempo:** la ficha del paciente se lee antes de decidir si queda tiempo; si no queda, no se envía nada.
13. [ ] **Comparación incompleta:** cada recuento que falta se escribe «no calculado» (por ejemplo «0 resueltos, reducidos: no calculado y 3 estables»).
14. [ ] **Los dos avisos nuevos de qué se envía** (panel y pie del informe), en los tres idiomas.
15. [ ] **Las notas fijas** cuando el texto se retiene o no se pide, incluida la nota de privacidad nueva.
16. [ ] **Pendiente que acepta dejar para otro cambio:** 6 controles antiguos (PRB-003 F5 y WF2, PRB-004 W11, versión 2026-10-25 I50, I53 e I55) ya estaban rotos antes de este cambio en archivos que no toca; no se cuentan como detectados.

### Pasos exactos para firmar

1. Lea esta lista y la descripción de la propuesta de cambio 78 en GitHub.
2. Rellene y firme `docs/iec62304/templates/TPL-03_Code_Review_Checklist.pdf` (revisión de código) y `TPL-11_Document_Approval.pdf` (documentos 02, 03, 05 y 09 y el manifiesto de pruebas).
3. En esos documentos, cambie cada «DRAFT, PENDING owner approval» por su aprobación, con su nombre y la fecha; guarde el cambio en la misma propuesta.
4. En GitHub, apruebe la revisión de la propuesta 78 (hace falta al menos una aprobación) y quítele el estado de borrador.
5. Espere a que las 7 pruebas de GitHub estén en verde y una la propuesta a la copia principal.
6. Publique el servidor (`bash scripts/deploy_backend.sh`, proyecto brain-mri-476110) y el frontal; con la decisión 2, deje `REPORT_LLM_ENABLED=false` y no ponga el nombre del modelo antiguo en `CLAUDE_MODEL`.
7. Después de publicar, pase `bash test_endpoints.sh` (9 de 9) y genere un informe de prueba; rellene `TPL-02_Release_Checklist.pdf`.
8. Fecha límite: **30-11-2026** (ese día se retira el modelo que usa hoy la aplicación).

## Qué cambia para el médico

- **Los números los escribe el programa, no la IA.** Recuento de lesiones (exacto por debajo de 20; por encima, el
  rango de MAGNIMS 2021), volumen, tamaños, regiones solo si un radiólogo las confirmó, diseminación en el espacio solo
  si se evaluó, y cambios entre visitas solo como «candidatos sin confirmar». Lo que no se calculó dice «no calculado»,
  nunca 0.
- **La IA solo añade dos comentarios cortos**, sin cifras, sin diagnóstico y sin tratamiento. Ya no hay apartado de
  «técnica» ni de «indicación clínica», que es donde la IA se inventaba datos.
- **Cada comentario se comprueba** frase a frase contra las mediciones. Si falla, se pide otra vez (dos veces como
  máximo). Si sigue fallando, el informe sale **solo con las medidas** y la nota «texto interpretativo retenido por la
  comprobación de seguridad».
- El texto que escribe el médico **sigue sin enviarse nunca** a la IA; tampoco se envían ya la edad ni el sexo.
- Cada intento queda en el registro de auditoría (sin el texto del informe).

## Por qué ahora

- El modelo que usa hoy la aplicación (`claude-sonnet-4-5-20250929`) **se retira el 30-11-2026**. Sin este cambio, el
  informe de IA deja de funcionar el 1-12-2026. El nuevo modelo es Claude Sonnet 5.5; el antiguo queda bloqueado.
- En nuestro estudio con datos públicos (452 casos), la plantilla de hoy falló en el 100 % de los borradores y habló
  de esclerosis múltiple en 97 de 97 cerebros sanos. El diseño nuevo: 0 fallos y nada faltante.

## Lo que usted revisa y firma

- [ ] **Requisitos** (documento 02): nuevos REQ-FUNC-116 y REQ-SAFE-048, 049, 050 y 051; cambios en REQ-FUNC-060,
      061 y 063 y en REQ-SEC-021. Tras la segunda revisión: cambios en REQ-SAFE-048 (comprobación más estricta), REQ-FUNC-116, REQ-SAFE-049 y 051, y propuestas en REQ-SEC-021 y 022.
- [ ] **Riesgos** (documento 03): peligro nuevo HAZ-017 (el modelo de IA es un componente de terceros que se retira);
      nuevas causas de HAZ-003 (apartado 3.11); controles nuevos RC-102 a RC-106; cambios en RC-064, RC-065 y RC-070.
- [ ] **Componentes de terceros** (documento 09): SOUP-BE-029 (Claude Sonnet 5.5) y SOUP-BE-030 (Claude Haiku 5.5);
      nota en SOUP-BE-011.
- [ ] **Matriz de trazabilidad** (documento 05) y **manifiesto de pruebas** de los controles.
- [ ] **Pruebas** (después de las cuatro revisiones independientes): 2957 pruebas unitarias del servidor pasan (29 omitidas porque no aplican); 112 de seguridad pasan; integración: 25 pasan y 1 falla porque en este ordenador falta el paquete `webauthn` (no tiene que ver con este cambio). Pantalla del informe: sin cambios en esta ronda; sus pruebas pasaron en la anterior. Todo sin conexión a la nube ni a la IA, una prueba detrás de otra para no cargar el portátil.
- [ ] **Controles negativos** (defectos introducidos a propósito, uno a uno): 67 de 67 detectados después de la segunda revisión; y 12 de 12 en la parte de la comprobación más estricta, repetida sobre el código final con el punto K. Se conservan los registros de las rondas anteriores (38 de 38 y 49 de 49).
- [ ] **Revisión independiente del código (10 puntos):** los 10 están corregidos. Para cada uno escribí primero una prueba que fallaba con el código revisado (15 de 15 fallaban) y después la corrección. Resumen: un informe con solo la diseminación ya no se rompe; una llamada a la IA ya no puede pasar de los 25 segundos; las medidas que el informe no usa ahora se nombran en el texto en vez de desaparecer; un recuento por región sin calcular ya no sale como 0; con 20 lesiones o más el comentario usa el rango de MAGNIMS; el informe ya no puede decir «sin confirmar» si la aplicación dice «confirmado»; las peticiones rechazadas también quedan en el registro de auditoría; se quitó un filtro que nunca actuaba; un solo mecanismo decide qué modelo se puede usar; los valores infinitos cuentan como «no calculado».
- [ ] **Segunda revisión independiente (10 puntos más uno):** todos corregidos; antes escribí pruebas que fallaban con el código revisado (51 de 60). Lo más importante: la comprobación de los comentarios de la IA es ahora **más estricta que la del estudio** y nunca más permisiva (lo comprueba una prueba con más de mil frases trampa). Una negación en otra parte de la frase ya no tapa un diagnóstico («esto no es un diagnóstico, pero el patrón es compatible con esclerosis múltiple» ahora se rechaza), y las líneas en negrita o en mayúsculas ya no se saltan la comprobación. Además: un valor raro en un dato que el informe no usa ya no bloquea el informe; las cuatro regiones MAGNIMS se cuentan aunque haya otras etiquetas; «diseminación no evaluada» sale una sola vez; ya no se envía a la IA la tabla de lesiones una a una.
- [ ] **Punto K** (lo encontró el trabajo de la plataforma de agentes): frases como «los hallazgos **cumplen** la diseminación en el espacio», en presente, negadas o con «podría». Si la diseminación no se evaluó, la aplicación ya las rechazaba; si se evaluó, una frase que contradecía el resultado pasaba (16 de 70 pruebas fallaban). Corregido.
- [ ] **Efecto medido sin gastar nada** (sin llamar a ninguna IA): repasé los 1204 borradores del estudio con la comprobación nueva. Solo 1 de 1181 borradores entregados quedaría marcado (una frase de aviso con la palabra «diagnóstico»; la IA tendría que reescribirla). Ninguno quedaría bloqueado con seguridad. Cero cerebros sanos afectados.
- [ ] **Tercera revisión independiente (6 puntos):** todos corregidos; antes escribí pruebas que fallaban con el código revisado (13 de 15 en el servidor y 14 de 14 en la pantalla). Lo más importante, el punto clínico que el revisor reprodujo: si el volumen venía solo en mL, el informe decía «volumen: no calculado» y luego el comentario de la IA daba «3,13 mL». Ahora hay una sola regla: la IA solo puede usar una cifra que el informe escrito por el programa ya dice. Además: cuando a la IA se le pidió el texto y no lo dio (tiempo agotado, fallo o negativa), el informe y la auditoría dicen «retenido», no «no pedido»; al acabar el tiempo, la petición a la IA se cancela de verdad; la pantalla ya no pone «Modelo: Claude» en un informe que solo tiene mediciones y muestra si los comentarios pasaron la comprobación, se retuvieron o no se pidieron; las plantillas antiguas salen del programa que se publica (quedan archivadas aparte).
- [ ] **Controles negativos de la tercera revisión** (solo los controles tocados, en una copia desechable): 16 de 16 defectos detectados en el servidor y 4 de 4 en la pantalla.
- [ ] **Cuarta revisión independiente (8 puntos):** todos corregidos; antes escribí pruebas que fallaban con el código revisado (40 de 40). Lo que cambia para el médico: un comentario vacío o con solo un punto ya no cuenta como «comentario comprobado» (se retiene); ningún marcador sin rellenar del tipo «{Total_Count}» o «[PLACEHOLDER]» puede llegar al informe (lo comprueba una prueba con más de 150 variantes); si el médico escribió la indicación clínica, el informe ya no dice que «no está disponible», sino que se muestra aparte y que el análisis automático no la usó; sin clave de la IA, el informe dice «no solicitado: no configurado», sin hablar de un fallo; un fallo de conexión con la IA ya no se confunde con un comentario rechazado; los caracteres invisibles ya no pueden esconder una frase a la comprobación.
- [ ] **Controles negativos de la cuarta revisión** (solo los controles tocados, en una copia desechable): 22 de 22 defectos detectados. La nueva puntuación de los borradores del estudio no cambia: 1 de 1181.
- [ ] **Quinta revisión independiente (10 puntos):** todos corregidos; antes escribí pruebas que fallaban con el código revisado (26 de 33; las otras 7 son de protección). Lo que cambia para el médico: los números escritos con letras («doce lesiones», «zwei neue Kandidaten», «ambas regiones») ya no pasan la comprobación, igual que las cifras; el borrador da el mismo número de candidatos nuevos que el aviso y la pantalla de revisión (solo los revisables); si la comprobación misma falla, el médico recibe las mediciones y los comentarios quedan retenidos (y queda registrado), en vez de un error; con la IA apagada o sin clave, el informe de mediciones sale aunque la ficha del paciente no se pueda leer; las limitaciones ya no dicen que faltan las imágenes con contraste o T1 cuando hay lesiones marcadas en ellas; un informe solo de volumen o solo de evolución ya no habla de diseminación en el espacio; la frase «diseminación no evaluada» la escribe una sola vez el propio informe.
- [ ] **Controles negativos de la quinta revisión** (solo los controles tocados, en una copia desechable): 28 de 28 defectos detectados.
- [ ] **Decisión suya — números escritos con letras:** al puntuar de nuevo, sin conexión, los borradores del estudio, 620 de 1181 usaban números con letras («entre veinte y cincuenta lesiones»); ahora se pedirían de nuevo (6 quedarían retenidos seguro). Las instrucciones a la IA solo dicen «no escribas cifras». Añadir «ni números con letras» reduciría las repeticiones, pero cambia el texto medido en el estudio y habría que medir otra vez. No lo he cambiado: lo decide usted.
- [ ] **Séptima revisión independiente — cambio de método:** en vez de corregir caso por caso, una batería prueba todas las combinaciones de datos de entrada (1128 casos) contra 8 reglas fijas. Antes de corregir fallaban muchas (por ejemplo, en 276 casos se perdía la frase «diseminación no evaluada» y en 360 el borrador hablaba de lesiones que no se habían pedido); ahora pasan todas. Lo que cambia para el médico: un informe solo de volumen ya no dice «número de lesiones: no calculado»; la frase de diseminación no evaluada aparece siempre que corresponde, una vez; el aviso sobre la marcación automática solo sale si la marcación fue automática; las lesiones nuevas demasiado pequeñas para revisar ya no desaparecen del borrador; si algo falla después de preguntar a la IA, el registro cuenta las preguntas reales.
- [ ] **Controles negativos de la séptima revisión:** 8 de 8 detectados.
- [ ] **Decisión suya (a) — texto de las lesiones pequeñas:** propuesta: «Además se marcaron {k} lesiones nuevas de menos de {d} mm; están por debajo del tamaño mínimo de revisión y no se propusieron como candidatos de cambio.» (también en inglés y alemán). ¿Lo aprueba o lo cambia?
- [ ] **Decisión suya (b) — cantidades con negación** («no hay lesiones grandes»): recomendación del coordinador: no rechazarlas (no son cantidades que puedan equivocarse en la dirección peligrosa).
- [ ] **Decisión suya (c) — instrucción «no escribas números con letras»:** recomendación: sí, pero solo junto con una nueva medición con el modelo de producción (Claude), que necesita su clave de investigación. Hasta entonces: comentarios de la IA APAGADOS al lanzar, y solo el borrador de mediciones escrito por el programa.
- [ ] **Octava revisión independiente — el programa ya no se contradice:** antes, partes del borrador escritas por el propio programa (la línea de lesiones pequeñas y el aviso de candidatos) no pasaban su propia comprobación, y entonces se pagaban tres preguntas a la IA para acabar reteniendo los comentarios; las instrucciones a la IA pedían una frase sobre la diseminación que la comprobación rechazaba; y la pantalla de revisión y el borrador podían dar resultados distintos si faltaba el número de lesiones estables. Ahora una batería lo comprueba en las 1128 combinaciones y en los tres idiomas, y todo pasa. Además: la ficha del paciente solo se lee si de verdad se va a preguntar a la IA; un informe solo de volumen ya no muestra un apartado «Impresión» vacío; un número escrito en otro idioma («two lesions» en un informe alemán) también se rechaza.
- [ ] **Controles negativos de la octava revisión:** 13 de 13 detectados; los guiones antiguos de CAPA-008 (17 de 17) y de la versión 2026-10-25 (7 de 10; 3 no detectados porque el informe verificado ya cubre ese fallo por otra vía, explicado en el guion) se volvieron a ejecutar.
- [ ] **Decisión suya (d) — fecha en el aviso de candidatos:** el aviso ya no cita la fecha de la medición de candidatos falsos (la comprobación no puede verificar una fecha y el control de privacidad rechaza fechas). La fuente sigue citada. ¿Lo aprueba?
- [ ] **Decisión suya (a), texto nuevo:** «Además se marcaron {k} lesiones nuevas de menos de {d} mm por debajo del tamaño mínimo de revisión, que no se propusieron como candidatos de cambio.»
- [ ] **Novena revisión independiente:** (1) desde 20 lesiones el borrador y lo que se envía a la IA ya solo dicen el rango MAGNIMS 2021 («20-50», «50-100», «>100»), nunca el número exacto; el número exacto queda solo en el análisis de lesiones de la aplicación; (2) si falta el bloque de candidatos de cambio, el borrador y la pantalla dicen «no calculado» en vez de contar como candidatos todas las lesiones nuevas; (3) con los comentarios de la IA apagados, una medida imposible (una fecha o un número de historia puesto como medida) ya no da un error «no enviado a la IA»: la petición se rechaza diciendo qué medida corregir, sin mostrar el valor; (4) el tiempo disponible para la IA se vuelve a calcular justo antes de preguntarle; (5) el archivo de la tasa de candidatos falsos se lee una sola vez, pero la comprobación de que sigue valiendo para la regla actual se hace siempre.
- [ ] **Controles negativos de la novena revisión:** 16 de 16 detectados (en la primera pasada 2 no se detectaron: la prueba no veía el número exacto dentro de los datos enviados a la IA; se reforzó la prueba y ya los detecta). Una prueba nueva revisa todos los guiones de controles: 13 controles antiguos apuntaban a código que ya no existe (se volvieron a anclar o se retiraron explicando qué los sustituye) y 1 «detección» antigua no era válida (el cambio fallaba por un nombre inexistente, no por la prueba). Repetidos en una copia desechable: CAPA-013 39 de 39, CAPA-014 1 de 1, PRB-003 1 de 1, versión 2026-10-25 1 de 1. Tres controles (PRB-003 F5 y WF2, PRB-004 W11) ya estaban rotos antes de este cambio en archivos que no toca: quedan pendientes, sin contarlos como detectados.
- [ ] **Decisión suya — número exacto desde 20 lesiones:** ¿aprueba que el borrador muestre solo el rango MAGNIMS y que el número exacto quede solo en el análisis de lesiones?
- [ ] **Decisión suya — medida imposible:** ¿aprueba que la petición se rechace (código 422) diciendo qué medida corregir, en lugar de escribir un borrador sin esa medida?
- [ ] **Décima revisión independiente:** (1) cada error del informe lleva ahora un código, y el panel muestra un mensaje propio para cada uno, en los tres idiomas — antes, una medida imposible salía como «No hay mediciones disponibles» aunque sí las había, y pedía «corregir la entrada» que el propio servidor había calculado (se habría visto al lanzar); (2) el registro de privacidad ya no dice «comprobado» antes de que las comprobaciones se hayan hecho, y si se cancela una pregunta a la IA queda igualmente registrada; (3) nunca se pregunta a la IA con menos de 5 segundos disponibles, tampoco al repetir, y si no da tiempo a repetir se dice que los comentarios no pasaron la comprobación (no «la IA no respondió»); (4) una petición que solo traía una decisión del lector (que el servidor no puede verificar y quita) ya no produce un informe vacío: se rechaza diciendo que no hay mediciones; (5) si una medida coincide con un número del paciente (historia, teléfono o fecha de nacimiento) se entrega el informe de mediciones con una nota, en vez de un error sin informe.
- [ ] **Controles negativos de la décima revisión:** informe 17 de 17 detectados; panel 3 de 3; los controles antiguos que apuntaban a código cambiado se volvieron a anclar y a ejecutar (CAPA-008 1 de 1, CAPA-014 5 de 5 —en la primera repetición uno no se detectó porque la prueba buscaba el texto antiguo de la petición; se reforzó—, versión 2026-10-25 2 de 2).
- [ ] **Decisión suya — texto que ve el médico ante una medida imposible** (ejemplo con el recuento de lesiones): en inglés «The lesion count computed by the segmentation analysis is outside its plausible range, so no draft was written. Re-run the analysis or check the segmentation. Nothing was sent to the AI service.»; en español «La medida «recuento de lesiones», calculada por el análisis de la segmentación, está fuera de su rango plausible, por lo que no se escribió ningún borrador. Vuelva a ejecutar el análisis o revise la segmentación. No se envió nada al servicio de IA.»; en alemán «Der Messwert „Läsionsanzahl“, berechnet von der Segmentierungsanalyse, liegt außerhalb seines plausiblen Bereichs; daher wurde kein Entwurf erstellt. Führen Sie die Analyse erneut aus oder prüfen Sie die Segmentierung. Es wurde nichts an den KI-Dienst gesendet.». ¿Lo aprueba?
- [ ] **Decisión suya — los otros 10 mensajes nuevos del panel** (en `frontend/src/i18n/locales`, apartado `report.errors`): ¿los aprueba?
- [ ] **Decisión suya — medida igual a un número del paciente:** ¿aprueba entregar el informe de mediciones con la nota de privacidad, sin preguntar a la IA, en lugar de un error?
- [ ] **Decisión suya — orden de la ficha y del tiempo:** la ficha del paciente se lee antes de decidir si queda tiempo para la IA (para descontar lo que tarda); si al final no queda tiempo no se envía nada. ¿Lo aprueba?
- [ ] **Pruebas en GitHub:** había un fallo que se repetía en GitHub desde la cuarta revisión (una prueba que buscaba «99999» y lo encontraba dentro del tiempo restante, 24,99999 segundos); corregida la prueba, no el programa.
- [ ] **Sexta revisión independiente (7 puntos, 2 clínicos):** todos corregidos; antes escribí pruebas que fallaban con el código revisado (35 de 48 en el servidor y 6 de 6 en la pantalla). Lo que cambia para el médico: si el número de candidatos nuevos falta, el borrador, su aviso y la pantalla dicen «no calculado» — antes el aviso y la pantalla decían «0 nuevos» contradiciendo al borrador; si el médico solo escribió la técnica o una observación, las limitaciones ya no dicen que escribió la indicación clínica; la comprobación de números con letras solo rechaza cantidades y medidas («dos lesiones», «cuatro pequeñas», «siete coma dos milímetros»), no «ambos hemisferios» ni «la primera visita»; si las mediciones tardan, la IA recibe solo el tiempo que queda de los 30 segundos y, si no queda bastante, sale el informe de mediciones (queda registrado).
- [ ] **Controles negativos de la sexta revisión:** 11 de 11 detectados (solo los puntos 1 a 3, en una copia desechable).
- [ ] **Decisión suya — cantidades dichas con «ningún», «no hay»:** la comprobación nueva rechaza las cantidades con números escritos en letra, pero no las que se dicen con una negación («no hay lesiones grandes», «ninguna grande»). ¿Se deben rechazar también? Puede aumentar las repeticiones.

## Decisiones que solo usted puede tomar

1. **Gravedad y probabilidad de HAZ-017.** Propuesta: moderada (S3); antes del cambio, frecuente (es seguro el
   30-11); después, remota.
2. **¿Encender los comentarios de la IA desde el primer día?** Claude todavía no se midió en el estudio (falta la
   clave de investigación). Opciones: (a) encenderlos ya: la comprobación protege igual, pero no sabemos cuántas veces
   retendrá el texto; (b) publicar con el interruptor apagado (`REPORT_LLM_ENABLED=false`): solo medidas, hasta medir
   Claude. Mi recomendación: (b) si la publicación es antes de medir.
3. **Respaldo automático del proveedor.** Lo dejé apagado a propósito: si Claude se niega, el proveedor podría
   contestar con otro modelo no validado. Hoy, si se niega, sale el informe con las medidas.
4. **El texto de las notas** cuando se retiene o no se pide el comentario (en español, inglés y alemán).

## Antes de publicar (fecha límite: 30-11-2026)

- Revisar y firmar lo de arriba; unir la propuesta de cambio; publicar el servidor.
- No poner `CLAUDE_MODEL` con el nombre antiguo (si no se pone nada, usa el nuevo).
- Después de publicar, pasar las 9 pruebas de `test_endpoints.sh` y generar un informe de prueba.

## Lo que no hice

- No medí Claude Sonnet 5.5 en el estudio (no hay clave de investigación); el diseño se midió con Gemini y Gemma.
- Ningún radiólogo ha leído todavía los textos que escribe el programa.
- La pantalla del informe aún no muestra el estado de la comprobación; la nota está dentro del texto.
- No actualicé la versión del cliente de Anthropic (0.44.0); los dos parámetros nuevos se envían de otra forma, ya
  probada sin conexión.
- No repetí las rondas completas de defectos de CAPA-014 (94) y PRB-003 (119): son muy pesadas e incluyen la pantalla. Actualicé sus puntos de anclaje para que sigan encontrando su sitio; 4 de PRB-003 ya estaban rotos antes de este cambio (G2, R10, F5, WF2). Lo que cambié en RC-064, RC-065 y RC-070 lo cubren defectos nuevos de la ronda del informe verificado.
- No escribí ninguna aprobación a su nombre: donde dice «PENDING owner approval», la aprobación la pone usted.
