# Artículo A — resumen para el dueño (versión 2, 04-11-2026)

## Qué es

Es el artículo científico completo, en inglés, sobre el "dial de lesiones falsas": una forma de
decirle al médico "de las lesiones que marca el programa, como mucho un X % son falsas". Lo
probamos con el mejor segmentador público de esclerosis múltiple (FLAMeS, sus cinco versiones
promediadas), en cinco grupos públicos de pacientes (304 resonancias de 245 pacientes) y en 100
personas sanas. Incluimos resonancias de cortes gruesos (4–8 mm), que son las habituales en muchos
hospitales.

La revista prevista es MELBA (artículo completo). La alternativa es una versión corta para el taller
UNSURE 2027 o para MICCAI.

## Qué cambió en esta versión

Un revisor independiente leyó la versión 1 y pidió una **revisión mayor**. Comprobó que las cifras
salían bien, salvo 8 redondeos con una milésima de error, pero dijo que el artículo se vendía mejor
de lo que mostraban los datos. Lo hemos corregido todo:

- **Título nuevo:** "La calibración con cortes finos no sirve para cortes gruesos". Ya no dice
  "pre-registrado" ni "el control medio aguanta".
- **El resumen dice ahora los veredictos fijados de antemano:**
  - el control medio, de cortes finos a gruesos, quedó **sin decidir**: no se vio ningún fallo, pero
    los datos no descartan hasta 1,8 veces lo prometido;
  - el control "en cada resonancia" **falló**.
- **El control medio parece mejor de lo que es.** Se mantiene bajo en parte porque cuenta como
  "sin error" las resonancias en las que el programa no marca nada. Cuando sí marca algo, el error
  sube: en el grupo de Irak, de media el 18,8 % de lo marcado era falso, frente al 10 % prometido.
  Y una de cada tres resonancias del grupo iraní superó el 10 % de lesiones falsas.
- **Somos honestos sobre el registro previo.** El protocolo se escribió 38 minutos antes de los
  resultados, en el ordenador, por la IA, y no se publicó antes que ellos. El artículo lo dice, y
  también que esa misma noche otro estudio analizó los mismos datos.
- **Intervalos más prudentes.** Con tan pocos pacientes (9–10 en dos grupos), esos grupos no se
  pueden clasificar.
- **El grosor de corte se presenta como lo que es:** una diferencia entre grupos de hospitales y
  aparatos, no un efecto demostrado del grosor.
- **"Hacen falta 10 pacientes del propio hospital"** se reescribió: eso sale del propio diseño del
  método, no es un hallazgo.
- **Redondeos:** se corrigieron los 8 que encontró el revisor y otros 4 que encontró nuestra propia
  comprobación, ahora más estricta. Todas las cifras salen de resultados sin redondear y se
  redondean una sola vez.
- **Análisis nuevos** (todos en el ordenador local, sin nube, anotados en el protocolo antes de
  ejecutarlos):
  - una simulación: muestra que el error extra con cortes gruesos viene del cambio de aparato, no
    de que las lesiones de una misma resonancia se parezcan entre sí;
  - comparación de métodos a igual capacidad de encontrar lesiones: quedan muy parecidos;
  - más repeticiones para medir el ruido de los sorteos;
  - la comparación de las cinco versiones del programa con los mismos candidatos.
- **Licencias:** ahora se dice que el laboratorio de Ljubljana da dos licencias distintas, y que los
  pesos de FLAMeS figuran como uso libre en un sitio (Zenodo) y como "no comercial" en otro
  (Hugging Face).
- **Bibliografía:** corregido el primer autor de MSLesSeg (Guarnera) y la cita de SibBMS (MELBA).
- **Autor:** Nicolás Bonilla Vargas (Universidad Nacional de Colombia; SRH University München;
  Daita AI). Conflicto de interés declarado: desarrollas MSTool-AI y estás vinculado a Daita AI.

## Qué hay en la carpeta

En `docs/research/paper/manuscript/`:

- `manuscript.md`: el artículo, versión 2.
- `RESPONSE_TO_REVIEW.md`: la respuesta al revisor, punto por punto (en inglés).
- `NUMBERS_CHECK.md`: cada número del texto con su origen. Las 219 comprobaciones pasan, contra
  resultados sin redondear.
- `figures/`: las 7 figuras con el estilo nuevo de la casa. En la figura 1 se distinguen ahora los
  casos que "cumplen" con el valor estimado por encima de lo prometido.
- `references.bib`, y `export/manuscript.docx` y `export/manuscript.pdf`.

Todo está guardado y subido a GitHub en la copia de trabajo `research/paper-a-manuscript`, sin unir
a la copia principal. No se tocó la aplicación.

## Lo que tienes que hacer tú (lista corta)

1. **Coautores:** un estadístico y un neurorradiólogo.
2. **Que una persona revise las cifras principales.** Hasta ahora solo las revisaron sesiones de la
   IA y el revisor independiente.
3. **Publicar el protocolo y el código en un archivo público con fecha** (OSF o Zenodo, con DOI),
   ahora mismo. En los próximos estudios, hacerlo *antes* de analizar.
4. **Licencias antes de vender:**
   - aclarar la de Ljubljana: la tarjeta de la aplicación usa cifras que incluyen 10 casos suyos;
   - aclarar la de los pesos de FLAMeS (uso libre en Zenodo, "no comercial" en Hugging Face): afecta
     a cualquier uso comercial del programa en el navegador;
   - aclarar la de SibBMS.
5. **Arreglar una incoherencia en los registros de la tarjeta:** el archivo de datos dice "pendiente
   de aprobación" y los documentos de requisitos dicen "aprobado".
6. **Completar la bibliografía en internet** (yo no puedo, trabajo sin conexión): nombres de pila de
   tres grupos de autores, listas completas de autores de cuatro obras, 11 identificadores DOI y el
   grosor de 3 mm de PediMS. La lista exacta está en `RESPONSE_TO_REVIEW.md`, apartado E.
7. **Rellenar** ORCID, financiación, permiso ético (normalmente no hace falta con datos públicos
   anónimos), y si el código será público y con qué licencia.
8. **Actualizar la búsqueda de artículos parecidos** justo antes de enviar.
9. **Opcional:** el brazo de LST-AI en los sanos; sanos de otro hospital leídos por un experto; y
   probar, con registro previo público, una calibración separada por tipo de aparato.
