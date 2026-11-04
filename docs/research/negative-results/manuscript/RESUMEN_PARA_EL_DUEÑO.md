# Resumen para el dueño — artículo de "resultados negativos"

## Qué es

Es un **borrador completo de artículo científico**, en inglés, listo para que lo revises. Cuenta dos
estudios nuestros que **no dieron la mejora que buscábamos**. Explica qué aprendimos y por qué eso le
sirve a otros grupos de investigación.

En los dos estudios dejamos escrito y guardado el plan **antes** de mirar ningún resultado: qué
íbamos a medir y cuánto tenía que mejorar algo para darlo por bueno. Eso es lo que da valor al
artículo: no podíamos "acomodar" los resultados después.

## Los dos estudios, en pocas palabras

**1. Enseñar a FLAMeS a leer resonancias de cortes gruesos.** Volvimos a entrenar FLAMeS (el modelo
que marca las lesiones) de dos maneras:

- **A:** con un truco que imita los cortes gruesos;
- **B:** sin el truco, como comparación.

El entrenamiento fue gratis, en las tarjetas gráficas de Kaggle. Evaluar costó 1,42 dólares en la
nube.

- En los tres hospitales con cortes gruesos, A mejoró un poco: +0,025 de acierto por lesión. El mínimo
  que habíamos fijado era +0,03, así que el resultado es **no concluyente**.
- A dio un 19 % menos de lesiones falsas.
- **El truco no aportó nada:** B, sin el truco, hizo lo mismo o mejor. La mejora venía de reentrenar
  con la colección MSLesSeg, no del truco.
- En resonancias finas de verdad (Ljubljana), A **empeoró mucho**: el parecido con el experto bajó
  0,17. Según la regla fijada de antemano, **no sirve para la aplicación**. No se usó.

**2. Un filtro aprendido para quitar lesiones falsas.** Lo probamos en tres fases, cada una con su
plan guardado antes.

- **Fase 3:** no llegó al mínimo fijado. Además descubrimos que el sistema reconocía **de qué hospital
  venía la imagen** casi a la perfección (0,98 sobre 1). Eso le hace aprender "el hospital" en vez de
  "la lesión".
- **Fase 3.1:** **sí llegó al mínimo** (de 0,72 a 0,83). Pero un análisis hecho después mostró que casi
  toda la mejora la da ya **juntar los 5 modelos de FLAMeS**, cosa que FLAMeS hace por defecto.
  Comparado con eso, el filtro solo añade +0,013. Es muy poco para meter una pieza nueva en un
  producto médico.
- **Fase 3.2, con 100 personas sanas:** no llegó al mínimo. El sistema aprendió a reconocer **al grupo
  de personas sanas** (0,85), no a distinguir mejor una lesión de verdad. Además, el filtro de la fase
  3.1 daba **más marcas falsas** en cerebros sanos que los 5 modelos juntos.
- **Decisión:** no se usó el filtro. Se mantienen los 5 modelos juntos.

## Las cuatro lecciones del artículo

1. Lo primero que aprende un modelo es **de qué hospital viene la imagen**. Hay que medirlo antes de
   entrenar y poner una barrera para ello.
2. Un reentrenamiento puede **parecer** el efecto de un truco. Solo un grupo de comparación idéntico
   pero sin el truco lo descubre. Además, un hospital "de casa" puede **esconder** una pérdida en otro.
3. Un filtro nuevo hay que compararlo con **los 5 modelos juntos**, tal como se usan, no con uno solo.
4. Escribir el plan antes **nos salvó dos veces de anunciar mejoras falsas**. Pero no basta: también
   hay que **publicar el plan antes** de hacer el trabajo, para que otros puedan comprobarlo.

## Revista recomendada

- **MELBA**, revista de inteligencia artificial para imagen médica. Publicar es gratis (comprobado el
  17-10-2026) y la leen justo las personas a quienes van dirigidas estas lecciones.
- **Alternativa: PLOS ONE.** Acepta resultados negativos, pero cobra por publicar.
- También se puede mandar una versión corta de 4 páginas a un taller llamado "I Can't Believe It's Not
  Better", si hay convocatoria abierta.

## Qué es honesto contar (y el artículo lo cuenta)

- En las fases 3 y 3.1, el plan se hizo público en internet **a la vez que los resultados**, no antes.
  La fecha guardada la pone el propio autor, así que otros no pueden comprobarla del todo. En el
  estudio 1 y en la fase 3.2 sí se publicó antes.
- Los valores de comparación **ya se conocían** de estudios anteriores nuestros. Cada plan lo
  declaraba.
- La licencia de Ljubljana resultó ser **solo para uso no comercial**. Lo descubrimos el 28-10, después
  de los estudios. Por eso nada de Ljubljana se usa en el producto.
- La inteligencia artificial (Claude) hizo gran parte del trabajo. El artículo lo declara con claridad
  y dice que la persona responsable eres tú.

## Cómo se comprobó que no hay números inventados

- Un programa saca **cada número** directamente de los archivos de resultados guardados. Otro
  programa comprueba que el texto dice exactamente lo mismo: **120 de 120 correctos**.
- Unos 25 datos más (fechas, tamaños de las colecciones) se comprobaron leyendo los planes. Están
  listados con su origen en `NUMBERS_CHECK.md`.
- Otro agente revisó el texto frase por frase contra los planes y resultados originales. Encontró 26
  puntos para mejorar (frases que decían más de lo que muestran los datos) y **todos se corrigieron**.
- Las figuras (6) salen de un programa que lee los resultados guardados. Usan colores que también
  distinguen las personas daltónicas.
- Guardamos una copia de las fechas que da GitHub, porque GitHub solo las muestra durante unos 90 días.

## Lo que falta que hagas tú (lista corta)

1. Poner tu afiliación, tu correo y los coautores, si hay alguno.
2. Leer y confirmar cómo se describe tu papel y el uso de la inteligencia artificial. No lo he firmado
   por ti.
3. Completar el conflicto de intereses (tu papel en MSTool-AI) y la financiación.
4. Decidir si se publican los dos modelos reentrenados (A y B). La licencia lo permite si se cita a los
   autores.
5. Elegir la licencia del código de investigación. El repositorio no tiene licencia todavía.
6. Antes de enviar: comprobar en internet 5 referencias marcadas "CHECK ONLINE" y guardar una copia
   del trabajo en Zenodo, para que tenga identificador permanente.

## Dónde está todo

Carpeta: `docs/research/negative-results/manuscript/`

- `manuscript.md`: el artículo.
- `references.bib`: la bibliografía.
- `figures/`: las 6 figuras, en imagen y en PDF.
- `NUMBERS_CHECK.md`: la comprobación de cada número.
- `scripts/`: los programas que sacan los números, hacen las figuras y comprueban el texto.
- `data/`: los números extraídos y la copia de las fechas de GitHub.

**No se generaron Word ni PDF del artículo**, porque el programa que los crea (pandoc) no está
instalado en este equipo.

Ningún cambio toca la aplicación ni el producto.
