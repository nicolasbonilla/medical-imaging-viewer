# Resumen para el dueño — artículo H (versión del 31-10-2026)

## Qué es

Un artículo científico que cuenta, con datos, cómo se ha construido MSTool-AI: un programa médico de
la clase de mayor riesgo (Clase C de la norma IEC 62304), hecho casi entero por un asistente de IA
bajo la dirección de una sola persona, usted. Es un "estudio de un caso": no compara con otros
equipos, describe este con todo detalle y con honestidad. Va dirigido a la revista *Empirical
Software Engineering* (la mejor opción) o al *Journal of Systems and Software*.

El borrador de octubre estaba atrasado. Esta versión llega hasta el 31-10-2026 e incluye todo lo que
pasó después: las pruebas de sabotaje, las revisiones independientes, el nuevo sistema de firmas y los
incidentes.

## Lo que dicen los datos, en pocas palabras

1. **El asistente lo hizo casi todo.** Lleva su marca en 525 de los 595 cambios guardados y en el
   99 % de las líneas añadidas, y en todos los cambios a los módulos de mayor riesgo. Usted dirige,
   decide, une los cambios y firma.
2. **Su fallo típico: pruebas que no podían fallar.** En abril, un resumen escrito por el asistente
   daba por comprobados 21 de 22 controles de riesgo; una revisión hecha para buscar fallos encontró
   que solo 4 lo estaban. Muchos fallos tardaron una mediana de 91 días en descubrirse.
3. **Las pruebas de sabotaje funcionan, pero no bastan.** En la última entrega se sembraron 873
   errores a propósito para comprobar que las pruebas los detectan: 868 detectados y 5 que no pueden
   cambiar nada. Aun así, hubo un control que nunca se ejecutaba aunque sus pruebas de sabotaje
   pasaban, y un error sembrado que dejó de quitar el control tras unir dos cambios. Además, los
   registros guardados solo muestran las ejecuciones limpias; los tropiezos solo se cuentan en el
   texto.
4. **Las revisiones independientes encuentran mucho.** 29 rondas de revisión, hechas por otras
   sesiones del mismo asistente, encontraron 189 problemas (2 que bloqueaban la entrega y 23 graves).
   Pero el fallo más serio para un radiólogo —lesiones que no se dibujaban mientras se aceptaba su
   confirmación— lo encontró una sesión que grababa la aplicación en el navegador para el vídeo
   comercial, no una revisión.
5. **Las aprobaciones.** Hasta el 21 de octubre, las 31 frases "aprobado por N. G. Bonilla Vargas"
   las escribía el asistente. Desde el 30 de octubre las firma usted en la web de GitHub, y GitHub las
   marca como verificadas: eso sí demuestra que fue usted. Pero la sustitución automática del texto
   "pendiente" también cambió frases que no eran casillas de aprobación. Ahora el plan de desarrollo
   dice que el asistente escribe su aprobación, un problema dice "aprobado y revisión de código" sin
   que hubiera revisión humana, y cuatro documentos de otro cambio quedaron como aprobados.
6. **Los incidentes los encontró el uso real, no las comprobaciones automáticas.** Las pruebas
   locales escribieron 62 cuentas de prueba en la base de usuarios de producción. Cualquiera podía
   registrarse y ver la lista de pacientes. Hubo contraseñas escritas en los registros del servidor y
   en el repositorio. Y hubo un envío al proyecto de nube equivocado. Las comprobaciones automáticas no
   podían ver ninguno de estos fallos.

## Qué cambia para usted y para los clientes

- Nada cambia hoy en la aplicación: este trabajo no toca el producto ni los documentos regulados.
- El artículo saca a la luz **defectos en los documentos regulados** que conviene corregir pronto
  (lista D de `OWNER_REVIEW.md`). El más importante: el plan de desarrollo, tal como está aprobado,
  ordena al asistente escribir su aprobación.
- También recuerda **tareas de producción pendientes que solo usted puede hacer**: borrar las cuentas
  de prueba, revisar quién vio la lista de pacientes, comprobar que se cambió la contraseña de
  administrador y revisar los registros del servidor.

## Lo que tiene que hacer usted (lista completa en `OWNER_REVIEW.md`)

1. Leer el artículo y hacerlo suyo; el texto lo escribió el asistente.
2. Conseguir una segunda persona que repita la clasificación de los fallos. Sin eso, la revista lo
   rechazará.
3. Confirmar los datos de los incidentes (puntos C1 a C10). Lo más urgente: cambiar la contraseña de
   administrador si no se hizo, y confirmar que el arreglo del registro abierto está publicado.
4. Decidir cómo corregir los documentos regulados afectados (puntos D1 a D7).

## Dónde está cada cosa

- El artículo: `docs/research/paper-h/manuscript/manuscript.md`
- Las 8 figuras y el programa que las dibuja: `docs/research/paper-h/manuscript/figures/`
- Las referencias (70, todas comprobadas una a una): `docs/research/paper-h/manuscript/references.bib`
- La comprobación de cada cifra: `docs/research/paper-h/manuscript/NUMBERS_CHECK.md`
- Lo que debe confirmar usted: `docs/research/paper-h/manuscript/OWNER_REVIEW.md`
- Los programas y los datos: `research/paper_h/`

No se pudo preparar la versión en Word ni en PDF porque el programa de conversión (pandoc) no está
instalado en este ordenador.
