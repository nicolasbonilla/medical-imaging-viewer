# Lista del dueño — informe de IA con comprobación automática (10-11-2026)

**Estado:** borrador para su revisión y firma. No se ha unido a la copia principal ni se ha publicado nada.
Propuesta de cambio en GitHub: {PR_LINK}

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
      061 y 063 y en REQ-SEC-021.
- [ ] **Riesgos** (documento 03): peligro nuevo HAZ-017 (el modelo de IA es un componente de terceros que se retira);
      nuevas causas de HAZ-003 (apartado 3.11); controles nuevos RC-102 a RC-106; cambios en RC-064, RC-065 y RC-070.
- [ ] **Componentes de terceros** (documento 09): SOUP-BE-029 (Claude Sonnet 5.5) y SOUP-BE-030 (Claude Haiku 5.5);
      nota en SOUP-BE-011.
- [ ] **Matriz de trazabilidad** (documento 05) y **manifiesto de pruebas** de los controles.
- [ ] **Pruebas:** 2727 pruebas unitarias del servidor pasan (10 omitidas: 9 casos que no aplican y la del cliente de Anthropic, que sí pasa con la versión fijada en otra corrida); 112 de seguridad pasan; integración: 25 pasan y 1 falla porque en este ordenador falta el paquete `webauthn` (no tiene que ver con este cambio). Todo sin conexión a la nube ni a la IA.
- [ ] **Controles negativos:** 38 de 38 defectos introducidos a propósito, uno a uno, fueron detectados por las pruebas (registro VERIFIED-REPORT_negative_controls_2026-11-10.json). En la primera corrida uno no se detectaba (la puerta de diseminación dentro del constructor del registro); añadí la prueba que faltaba y la segunda corrida detectó los 38.

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
- No escribí ninguna aprobación a su nombre: donde dice «PENDING owner approval», la aprobación la pone usted.
