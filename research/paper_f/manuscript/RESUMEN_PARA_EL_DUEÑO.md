# Artículo F — resumen para el dueño (una página)

**Qué preguntamos.** Muchos hospitales guardan resonancias FLAIR de **cortes gruesos** (de 4 a 8 mm).
Queríamos saber si alguna herramienta pública que funciona sin tarjeta gráfica (MindGlide,
WMH-SynthSeg, SAMSEG y, en cortes finos, LST-AI) marca las lesiones de esclerosis múltiple **mejor que
FLAMeS**, el modelo que ya usamos.

**Cómo.** Dejamos escritas y publicadas todas las reglas el 21-10-2026, **40 minutos antes** de que
corriera la primera herramienta (GitHub lo registra). Usamos 324 estudios de 5 colecciones públicas
con lesiones marcadas por expertos: 179 de cortes gruesos y 145 de cortes de 1 mm. Todas las
herramientas recibieron exactamente la misma imagen.

**Resultado: la idea no se confirmó (resultado negativo, contado con honestidad).**
- En cortes gruesos **ninguna herramienta supera a FLAMeS**. Todas aciertan claramente menos
  lesiones: de 100 puntos de acierto de FLAMeS (0,72), MindGlide pierde 17, SAMSEG 24 y
  WMH-SynthSeg 38.
- SAMSEG y WMH-SynthSeg marcan **menos lesiones falsas**, pero solo porque marcan muy poco: encuentran
  apenas **6 % y 5 %** de las lesiones pequeñas, frente al **49 %** de FLAMeS.
- En cortes de 1 mm FLAMeS también es la mejor (LST-AI queda por debajo).
- MindGlide empeora menos que FLAMeS al pasar de cortes finos a gruesos, pero sigue por debajo.
- Idea para el futuro (sin validar): cuando MindGlide y FLAMeS **no coinciden**, suele ser un estudio
  donde FLAMeS falla. Sirve como pista para una "segunda opinión", pero se basa en solo 14 estudios.
- **No afirmamos ninguna utilidad clínica.** Coste total de cálculo: **12,55 USD** de crédito gratuito.

**Qué se entrega** (carpeta `research/paper_f/manuscript/`): el artículo completo en inglés
(`manuscript.md`, `.docx` y `.pdf`, unas 5.300 palabras), 4 figuras aptas para daltónicos, 44
referencias **todas comprobadas una a una** en sus fuentes, y `NUMBERS_CHECK.md`: un programa
comprueba **362 cifras** del texto contra sus archivos de origen; **todas cuadran**.

**Revista elegida:** *NeuroImage: Clinical*. **Alternativa:** *MELBA* (Machine Learning for
Biomedical Imaging), que valora los resultados negativos reproducibles.

**Dos cosas que encontré y corregí al escribir (por transparencia):**
1. El 22-10 se hizo un **análisis intermedio** de MindGlide que el protocolo no preveía y que no se
   anotó entonces. Lo declaro en la tabla de cambios del artículo y lo añadí al registro de cambios
   del protocolo. No cambia ningún resultado.
2. El informe de resultados decía "6,8–9,8 mL" para SAMSEG; lo correcto es **6,8–9,7 mL** (redondeo
   doble). El artículo usa el valor correcto.

**Lo que solo tú puedes hacer (lista corta, todo de una vez):**
1. Coautores, sus identificadores ORCID y el correo de contacto.
2. La afiliación exacta (nombre legal, ciudad, país).
3. Confirmar el texto sobre uso de IA y **quién lanzó cada trabajo en la nube**; revisar y hacer tuyo
   cada párrafo (eres el responsable del contenido).
4. Confirmar conflicto de intereses, contribuciones de cada autor y si la revista o tu institución
   piden una declaración formal de ética (usamos solo datos públicos y anónimos).
5. Poner una licencia al repositorio y archivar una versión con DOI (por ejemplo en Zenodo); decidir
   si se publican también las máscaras de las herramientas.
6. Rellenar la lista de comprobación CLAIM 2024.
7. Mirar la versión de nnU-Net en el archivo de entorno guardado en el cubo de investigación
   (no quedó anotada en los registros).
8. Confirmar dos licencias: la versión exacta de la de Ljubljana y la de los pesos de HD-BET.
9. Revisar las normas de la revista (largo del resumen, estilo de referencias) antes de enviar.
