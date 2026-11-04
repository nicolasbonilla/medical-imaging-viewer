# Artículo F — resumen para el dueño (una página; versión 1.1, revisada tras la revisión interna)

**Qué preguntamos.** Muchos hospitales guardan resonancias FLAIR de **cortes gruesos** (de 4 a 8 mm).
Comparamos tres herramientas públicas que funcionan sin tarjeta gráfica (MindGlide, WMH-SynthSeg y
SAMSEG; LST-AI solo en cortes finos) con **FLAMeS**, el modelo que ya usa MSTool-AI.

**Cómo.** Las reglas se escribieron y publicaron el 21-10-2026, **40 minutos antes** de que se pusiera
en marcha la primera herramienta (GitHub lo registra). Usamos 324 estudios de 5 colecciones públicas
con lesiones marcadas por expertos: 179 de cortes gruesos y 145 en una rejilla de 1 mm. Las preguntas
eran "¿hay diferencia, en un sentido u otro?", no "¿gana alguna herramienta?".

**Qué salió.**
- En cortes gruesos **FLAMeS acierta claramente más lesiones que las tres herramientas**. De sus 0,72
  puntos de acierto, MindGlide se queda 0,17 por debajo, SAMSEG 0,24 y WMH-SynthSeg 0,38. Ocurre en
  todas las colecciones.
- SAMSEG y WMH-SynthSeg marcan **menos lesiones falsas**, pero solo porque marcan muy poco: encuentran
  el 6 % y el 5 % de las lesiones pequeñas, frente al 49 % de FLAMeS.
- Según la regla fijada de antemano, ninguna herramienta "gana" a FLAMeS ni empata con ella. En la
  rejilla de 1 mm FLAMeS también es la mejor; LST-AI queda por debajo.
- Dato nuevo: FLAMeS **nunca vio cortes gruesos al entrenarse** (su "huella" pública lo demuestra), y
  aun así es la mejor en ellos.
- **No afirmamos ninguna utilidad clínica.** Coste: 12,55 USD propios; 19,84 USD contando cálculos
  anteriores que se reutilizaron.

**Qué cambió tras la revisión (todo con cálculos sin nube; las 480 cifras del texto cuadran):**
1. Se quitó el lenguaje de "hipótesis" y de "resultado negativo": el protocolo no lo decía.
2. Se retiró la afirmación de que **"MindGlide empeora menos con cortes gruesos"**. Su acierto
   *sube* en las colecciones de cortes gruesos, lo que apunta a diferencias entre colecciones y no al
   grosor. Además, la banda de "1 mm" es sobre todo MSLesSeg, adquirida con cortes de unos 2,6 mm.
3. **La "segunda opinión" queda descartada.** Contar cuántas lesiones marca FLAMeS señala mejor los
   estudios dudosos (0,93) que comparar con MindGlide (0,78). `APP-FEATURE.md` está actualizado.
4. **Conflicto de intereses reescrito**: el resultado favorece a tu producto, que ya usa FLAMeS, y se
   declaran las funciones de la app previstas con estas cifras.
5. **Licencias.** Ljubljana es **no comercial y sin obras derivadas** (CC BY-NC-ND), así que no se
   publican máscaras suyas. Los pesos de HD-BET son **no comerciales** y se usaron en 151 de los 179
   estudios de cortes gruesos; por eso el aviso de fiabilidad en la app queda bloqueado hasta resolver
   la licencia.
6. **Uso de IA** según las normas de Elsevier: el papel del agente se describe en Métodos, y la
   declaración va justo antes de las referencias. Ya **no** se dice que revisaste o aprobaste el
   protocolo: eso lo tienes que confirmar tú.

**Lo que solo tú puedes hacer (todo de una vez):**
1. Coautores, ORCID, correo de contacto y el detalle de tus tres afiliaciones (departamento, ciudad,
   país).
2. Confirmar si revisaste y aprobaste el protocolo y sus cambios, quién lanzó cada trabajo en la nube,
   y la frase "revisé y edité el texto y asumo la responsabilidad".
3. Confirmar el conflicto de intereses (también cualquier interés en Daita AI o SRH) y tus roles de
   autor; valorar un coautor o estadístico independiente que audite el análisis.
4. Archivar el protocolo de 65a95e3 en OSF o Zenodo con DOI, y decidir si se archiva el extracto del
   registro de la sesión que fecha la comprobación del 29-10 (00:01:59 UTC).
5. Poner una licencia al repositorio, archivar una versión con DOI y decidir qué máscaras se publican
   (nunca las de Ljubljana).
6. Rellenar la lista CLAIM 2024 y mirar la versión de nnU-Net en el archivo de entorno del cubo.
7. Revisar las normas de la revista. El texto principal tiene unas 6.700 palabras; la revisión añadió
   contenido obligatorio.
