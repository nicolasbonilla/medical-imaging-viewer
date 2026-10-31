# Artículo A — resumen para el dueño (31-10-2026)

## Qué es

Es el artículo científico completo, en inglés, sobre el "dial de lesiones falsas": una forma de
decirle al médico "de las lesiones que marca el programa, como mucho un X % son falsas". Lo
probamos con el mejor segmentador público de esclerosis múltiple (FLAMeS, sus cinco versiones
promediadas), en cinco grupos públicos de pacientes (304 resonancias de 245 pacientes) y en 100
personas sanas. Incluimos resonancias de cortes gruesos (4–8 mm), que son las habituales en muchos
hospitales.

La revista prevista es MELBA (artículo completo). La alternativa es una versión corta para el taller
UNSURE 2027 o para MICCAI.

## Qué dice, en cuatro frases

1. **Lo que aguanta:** de media, el dial cumple lo que promete también en hospitales que el programa
   no vio y con cortes gruesos. Mejor dicho, no encontramos ningún fallo. Eso no demuestra que
   funcione: en un hospital el resultado quedó sin decidir.
2. **Lo que falla:** la promesa "en cada resonancia" no aguanta. Calibrada con cortes finos y usada
   con cortes gruesos, falla en el 21–29 % de las resonancias, cuando el límite era el 10 %. Solo se
   arregla con al menos 10 pacientes del propio hospital, y entonces el programa casi no marca nada
   (encuentra menos del 4 % de las lesiones).
3. **Promediar las cinco versiones del programa** duplica las lesiones que se encuentran, pero no
   arregla la fiabilidad: mejoró un hospital y empeoró otro.
4. **En cerebros sanos**, el programa sin filtro marca alguna "lesión" en 85 de 100 personas. La
   regla de diseminación en el espacio de nuestra aplicación saldría positiva en 19 de 100 sanos.
   Por eso nunca debe calcularse sin que un médico revise antes las lesiones.

El efecto del grosor de corte está mezclado con el del hospital: cada grosor viene casi siempre de
un hospital distinto. El artículo lo dice claramente.

## Qué corregimos respecto a los borradores anteriores

- Ya no usamos como prueba "externa" resonancias con las que FLAMeS se entrenó. Ljubljana tiene 20
  de sus 30 casos dentro del entrenamiento, e ISBI-2015 está entero dentro. ISBI-2015 se ha quitado
  por completo. De Ljubljana solo usamos los 10 casos limpios, y avisamos de que el hospital sí
  estaba en el entrenamiento. Además lo comprobamos quitando Ljubljana del todo: los resultados no
  cambian.
- Quitamos la frase antigua "0 de 200 sanos con diseminación (como mucho 1,8 %)". Eran 20 repartos
  de las mismas 30 personas; con 30 personas el techo honrado es de un 10 %. Ahora damos las cifras
  de 100 sanos distintos.
- Encontramos un error en los documentos anteriores: decían que el método principal era el único
  sin ningún fallo detectado. Otro método (Learn-then-Test) tampoco tenía fallos. Está corregido.
- Añadimos dos métodos de comparación que pedía la revisión: "un candidato por paciente" y los
  "valores e jerárquicos". Se calcularon después de ver los resultados, y así se dice. El segundo
  no marca nada con cortes gruesos.
- El método "por resonancia" (CALM-FDX) se presenta como una aplicación de técnicas conocidas, no
  como teoría nueva.

## Qué hay en la carpeta

En `docs/research/paper/manuscript/`:

- `manuscript.md`: el artículo, con resumen estructurado, métodos, resultados, limitaciones, tabla
  de desviaciones del protocolo, ética, licencias y declaraciones.
- `figures/`: 7 figuras hechas por un programa a partir de los resultados guardados, con colores
  aptos para daltónicos.
- `references.bib`: 56 referencias, todas comprobadas contra fuentes. Cuatro tienen un dato que
  revisar (ver más abajo).
- `NUMBERS_CHECK.md`: cada número del texto, con el archivo exacto del que sale. Las 186
  comprobaciones pasan, y las tablas se generan solas desde los resultados.
- `export/manuscript.docx` y `export/manuscript.pdf`: versiones en Word y PDF, hechas sin internet.
- `RESUMEN_PARA_EL_DUEÑO.md`: este documento.

Todo está guardado y subido a GitHub en la copia de trabajo `research/paper-a-manuscript`, sin unir
a la copia principal. No se tocó la aplicación ni se usó la nube: todo se calculó en el ordenador
local.

## Lo que la aplicación ya hace con esto

La tarjeta "fiabilidad por grosor de corte" ya existe en la aplicación, **apagada por defecto**:

- dice el grosor real de la resonancia;
- dice qué tamaño de lesión se suele encontrar con ese grosor;
- avisa de que una lista vacía no significa que no haya lesiones;
- **no muestra ningún porcentaje de lesiones falsas**.

El artículo la presenta como traslado a la práctica, no como validación clínica.

## Lo que tienes que hacer tú (lista corta)

1. **Coautores:** buscar un estadístico y un neurorradiólogo. El artículo lo recomienda antes de
   enviarlo.
2. **Una revisión humana de las cifras principales.** Las dos comprobaciones independientes las hizo
   otra sesión de la IA, no una persona. Además, el código de la comprobación de pacientes no quedó
   guardado en el repositorio.
3. **Rellenar los datos que faltan:**
   - afiliación, ORCID y correo de contacto;
   - financiación y posibles conflictos de interés (eres el creador de MSTool-AI);
   - si tu institución exige un permiso ético (normalmente no, con datos públicos anónimos);
   - si el repositorio será público, con qué licencia, y una copia con DOI.
4. **Licencias antes de vender:**
   - La página del laboratorio de Ljubljana dice "no comercial y sin obras derivadas". La tarjeta de
     la aplicación usa cifras de la franja de cortes finos que incluyen 10 casos de Ljubljana. Antes
     de encender la tarjeta en el producto que se vende, hay que aclarar esa licencia o rehacer la
     franja sin Ljubljana.
   - Los sanos (SibBMS) tienen dos licencias distintas escritas. Tampoco pueden usarse en el
     producto hasta aclararlo.
5. **Revisar cuatro referencias marcadas** (OWNER-CHECK en `references.bib`):
   - el volumen de Jin y Candès;
   - las páginas de Barber et al.;
   - los datos de la revista de HD-BET;
   - el título exacto del artículo de MSLesSeg.
6. **Actualizar la búsqueda de artículos parecidos** justo antes de enviar. La de octubre se hizo en
   parte sin acceso completo a internet.
7. **Para el próximo estudio:** registrar el protocolo en un registro público (por ejemplo OSF)
   *antes* de analizar. Esta vez el protocolo principal solo llegó a GitHub junto con los primeros
   resultados, y el artículo lo dice. El anexo de los sanos sí llegó 71 minutos antes de sus
   resultados.
8. **Opcional, y mejoraría el artículo:**
   - el brazo de LST-AI en los sanos;
   - sanos de otro hospital, leídos por un experto;
   - probar una calibración separada por tipo de adquisición, registrada de antemano.
