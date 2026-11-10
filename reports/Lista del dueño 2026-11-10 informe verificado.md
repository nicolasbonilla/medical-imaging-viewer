# Lista del dueño — informe de IA con comprobación automática (10-11-2026)

**Estado:** borrador para su revisión y firma. No se ha unido a la copia principal ni se ha publicado nada.
Propuesta de cambio en GitHub: https://github.com/nicolasbonilla/medical-imaging-viewer/pull/78 (borrador)

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
- [ ] **Pruebas** (después de las tres revisiones independientes): 2908 pruebas unitarias del servidor pasan (26 omitidas porque no aplican; una que fallaba tras la tercera revisión ya está corregida y su archivo vuelto a pasar); 112 de seguridad pasan; integración: 25 pasan y 1 falla porque en este ordenador falta el paquete `webauthn` (no tiene que ver con este cambio). Pantalla del informe: 14 pruebas nuevas y 13 que ya existían pasan. Todo sin conexión a la nube ni a la IA, una prueba detrás de otra para no cargar el portátil.
- [ ] **Controles negativos** (defectos introducidos a propósito, uno a uno): 67 de 67 detectados después de la segunda revisión; y 12 de 12 en la parte de la comprobación más estricta, repetida sobre el código final con el punto K. Se conservan los registros de las rondas anteriores (38 de 38 y 49 de 49).
- [ ] **Revisión independiente del código (10 puntos):** los 10 están corregidos. Para cada uno escribí primero una prueba que fallaba con el código revisado (15 de 15 fallaban) y después la corrección. Resumen: un informe con solo la diseminación ya no se rompe; una llamada a la IA ya no puede pasar de los 25 segundos; las medidas que el informe no usa ahora se nombran en el texto en vez de desaparecer; un recuento por región sin calcular ya no sale como 0; con 20 lesiones o más el comentario usa el rango de MAGNIMS; el informe ya no puede decir «sin confirmar» si la aplicación dice «confirmado»; las peticiones rechazadas también quedan en el registro de auditoría; se quitó un filtro que nunca actuaba; un solo mecanismo decide qué modelo se puede usar; los valores infinitos cuentan como «no calculado».
- [ ] **Segunda revisión independiente (10 puntos más uno):** todos corregidos; antes escribí pruebas que fallaban con el código revisado (51 de 60). Lo más importante: la comprobación de los comentarios de la IA es ahora **más estricta que la del estudio** y nunca más permisiva (lo comprueba una prueba con más de mil frases trampa). Una negación en otra parte de la frase ya no tapa un diagnóstico («esto no es un diagnóstico, pero el patrón es compatible con esclerosis múltiple» ahora se rechaza), y las líneas en negrita o en mayúsculas ya no se saltan la comprobación. Además: un valor raro en un dato que el informe no usa ya no bloquea el informe; las cuatro regiones MAGNIMS se cuentan aunque haya otras etiquetas; «diseminación no evaluada» sale una sola vez; ya no se envía a la IA la tabla de lesiones una a una.
- [ ] **Punto K** (lo encontró el trabajo de la plataforma de agentes): frases como «los hallazgos **cumplen** la diseminación en el espacio», en presente, negadas o con «podría». Si la diseminación no se evaluó, la aplicación ya las rechazaba; si se evaluó, una frase que contradecía el resultado pasaba (16 de 70 pruebas fallaban). Corregido.
- [ ] **Efecto medido sin gastar nada** (sin llamar a ninguna IA): repasé los 1204 borradores del estudio con la comprobación nueva. Solo 1 de 1181 borradores entregados quedaría marcado (una frase de aviso con la palabra «diagnóstico»; la IA tendría que reescribirla). Ninguno quedaría bloqueado con seguridad. Cero cerebros sanos afectados.
- [ ] **Tercera revisión independiente (6 puntos):** todos corregidos; antes escribí pruebas que fallaban con el código revisado (13 de 15 en el servidor y 14 de 14 en la pantalla). Lo más importante, el punto clínico que el revisor reprodujo: si el volumen venía solo en mL, el informe decía «volumen: no calculado» y luego el comentario de la IA daba «3,13 mL». Ahora hay una sola regla: la IA solo puede usar una cifra que el informe escrito por el programa ya dice. Además: cuando a la IA se le pidió el texto y no lo dio (tiempo agotado, fallo o negativa), el informe y la auditoría dicen «retenido», no «no pedido»; al acabar el tiempo, la petición a la IA se cancela de verdad; la pantalla ya no pone «Modelo: Claude» en un informe que solo tiene mediciones y muestra si los comentarios pasaron la comprobación, se retuvieron o no se pidieron; las plantillas antiguas salen del programa que se publica (quedan archivadas aparte).
- [ ] **Controles negativos de la tercera revisión** (solo los controles tocados, en una copia desechable): 16 de 16 defectos detectados en el servidor y 4 de 4 en la pantalla.

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
