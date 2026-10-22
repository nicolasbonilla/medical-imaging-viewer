# Registro de cómputo de la investigación MSTool-AI

Generado el 2026-10-22 18:58 UTC con `research/cloud/build_ledger.py`. Precios: **precio oficial de lista de Google Cloud en USD** (Cloud Billing Catalog API, consultado el mismo día, con el código SKU de cada parte en `records/`). Cambio: 1 EUR = 1.1205 USD (tipo de referencia del BCE del 2026-10-22). Google factura en EUR con su propio cambio; la cifra exacta se cruza después con el informe de facturación.

## Resumen

| Concepto | Valor |
|---|---|
| Corridas en la nube con tiempo medido | 20 en mstool-research · 9 en agosto (brain-mri-476110) |
| Horas de máquina, proyecto de investigación | 65.84 h |
| Coste a precio de lista, proyecto de investigación | 11.60 USD ≈ 10.35 EUR |
| Almacenamiento en el cubo (hoy) | 5.37 GB ≈ 0.107 USD/mes |
| Crédito gratuito usado (estimado) | 10.45 EUR de 264 EUR (tope propio 240 EUR; caduca 2027-01-15) — quedan ≈ 229.55 EUR |
| Horas de máquina, agosto (proyecto de la app) | 7.50 h · registrado 0.86 USD · a precio de lista de hoy 1.69 USD (pagado por la cuenta de la app, no por el crédito) |

## Máquinas usadas

| Máquina | Procesador | vCPU | Memoria (GB) | Tarjeta gráfica | Modalidad | USD/hora (lista) |
|---|---|---|---|---|---|---|
| e2-standard-8 | no registrado | 8 | 32.0 | — | Spot (interrumpible) | 0.1614 |
| n1-standard-4 | no registrado | 4 | 15.0 | nvidia-tesla-p4:1 | Spot (interrumpible) | 0.34452 |
| n2-standard-8 | no registrado | 8 | 32.0 | — | Spot (interrumpible) | 0.23987 |
| n2d-standard-4 | AMD Milan — AMD EPYC 7B13 | 4 | 16.0 | — | estándar | 0.17583 |
| n2-standard-4 | Intel Cascade Lake — Intel(R) Xeon(R) CPU @ 2.80GHz | 4 | 16.0 | — | estándar | 0.20109 |
| e2-standard-4 | Intel Broadwell — Intel(R) Xeon(R) CPU @ 2.20GHz | 4 | 16.0 | — | estándar | 0.14772 |

## Todas las corridas

| Fecha | Corrida | Para qué | Máquina | Procesador | Modalidad | Duración (h:mm:ss) | Preparación / cálculo | Casos ok / fallos | s por caso | Coste lista USD | Registrado USD | Estado |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-08-17 | phase1-lstai | Fase 1: mapas de probabilidad de LST-AI en 19 casos ISBI | e2-standard-8 | no registrado | Spot (interrumpible) | 0:38:00 | — / — | — / — | — | 0.0968 | 0.1200 | correcta |
| 2026-08-17 | flames-pilot | FLAMeS, piloto 1 de agosto: 3 casos de principio a fin | e2-standard-8 | no registrado | Spot (interrumpible) | 0:17:33 | — / — | — / — | — | 0.0471 | 0.0292 | fallida (errores del piloto corregidos) |
| 2026-08-17 | flames-pilot2 | FLAMeS, piloto 2 de agosto | e2-standard-8 | no registrado | Spot (interrumpible) | 0:12:42 | — / — | — / — | — | 0.0342 | 0.0212 | fallida (errores del piloto corregidos) |
| 2026-08-17 | flames-pilot3 | FLAMeS, piloto 3 de agosto | e2-standard-8 | no registrado | Spot (interrumpible) | 0:22:19 | — / — | — / — | — | 0.0600 | 0.0372 | fallida (errores del piloto corregidos) |
| 2026-08-17 | flames-pilot4-gpu | FLAMeS, piloto 4 de agosto con tarjeta gráfica NVIDIA P4 | n1-standard-4 | no registrado | Spot (interrumpible) | 0:25:49 | — / — | — / — | — | 0.1483 | 0.0947 | fallida (errores del piloto corregidos) |
| 2026-08-17 | flames-pilot5-cpu | FLAMeS, piloto 5 de agosto solo con procesador (validado) | e2-standard-8 | no registrado | Spot (interrumpible) | 0:26:06 | — / — | — / — | — | 0.0702 | 0.0435 | correcta |
| 2026-08-17 | flames-full | FLAMeS completo de agosto: mapas de 145 casos (30 Ljubljana + 115 MSLesSeg) | n1-standard-4 | no registrado | Spot (interrumpible) | — | — / — | — / — | — | — | — | sin tiempo registrado |
| 2026-08-17 | flames-controls | FLAMeS en 100 controles sanos SibBMS (planificada en agosto) | n1-standard-8 | no registrado | Spot (interrumpible) | — | — / — | — / — | — | — | — | sin tiempo registrado |
| 2026-08-17 | sibbms-pilot | Piloto SibBMS: 3 controles sanos (sustituida por sibbms-pilots) | n2-standard-8 | no registrado | Spot (interrumpible) | — | — / — | — / — | — | — | — | sin tiempo registrado |
| 2026-08-17 | flames-backfill | MSLesSeg: los 22 casos de prueba que faltaban | n2-standard-8 | no registrado | Spot (interrumpible) | 0:59:30 | — / — | — / — | — | 0.2375 | 0.0990 | correcta |
| 2026-08-17 | sibbms-pilots | Validación de la cadena de controles sanos SibBMS (2 pilotos) | n2-standard-8 | no registrado | Spot (interrumpible) | 0:59:11 | — / — | — / — | — | 0.2375 | 0.0990 | correcta |
| 2026-08-17 | sibbms-full | Controles sanos SibBMS en 4 máquinas en paralelo | 4 × n2-standard-8 | no registrado | Spot (interrumpible) | 1:06:00 | — / — | — / — | — | 0.7628 | 0.3180 | correcta |
| 2026-10-17 | flames-extra-pilot | Piloto de colecciones nuevas: un caso de MS3SEG, Bagdad y PediMS; HD-BET + FLAMeS modelo 0 | n2d-standard-4 | AMD Milan | estándar | 0:24:36 | 0:21:08 / 0:03:27 | 3 / 0 | 66.3 | 0.0721 | 0.0721 | correcta |
| 2026-10-17 | flames-full-a | FLAMeS, 5 modelos por separado, bloque A (casos 1 a 49 de 145) | n2d-standard-4 | AMD Milan | estándar | 4:46:52 | 0:04:04 / 4:42:47 | 245 / 0 | 69.1 | 0.8407 | 0.8407 | correcta |
| 2026-10-17 | flames-full-b | FLAMeS, 5 modelos por separado, bloque B (casos 50 a 97 de 145) | n2d-standard-4 | AMD Milan | estándar | 5:00:23 | 0:02:45 / 4:57:37 | 240 / 0 | 68.7 | 0.8803 | 0.8803 | correcta |
| 2026-10-17 | flames-full-c | FLAMeS, 5 modelos por separado, bloque C (casos 98 a 145) | n2-standard-4 | Intel Cascade Lake | estándar | 4:26:53 | 0:04:11 / 4:22:41 | 234 / 0 | 68.5 | 0.8945 | 0.8945 | correcta |
| 2026-10-17 | flames-pilot-1 | Piloto v1 en la nube de investigación (Spot): FLAMeS modelo 0 en casos de Ljubljana, comparado con agosto | n2-standard-8 | no registrado | Spot (interrumpible) | 0:20:58 | — / — | — / — | — | 0.0838 | 0.0280 | correcta |
| 2026-10-17 | flames-v2-pilot | Piloto v2 (máquina estándar, datos guardados en el cubo): 2 casos de Ljubljana, modelo 0 | n2-standard-4 | Intel Cascade Lake | estándar | 0:18:22 | — / — | 0 / 0 | — | 0.0616 | 0.0582 | fallida (entorno de software) |
| 2026-10-17 | flames-v2-pilot2 | Piloto v2 corregido: 2 casos de Ljubljana, modelo 0, comparado con agosto | n2-standard-4 | Intel Cascade Lake | estándar | 0:04:55 | 0:02:30 / 0:02:23 | 2 / 0 | 65.5 | 0.0165 | 0.0165 | correcta |
| 2026-10-17 | lstai-pilot | Piloto LST-AI v1.2.0: MSLesSeg P10_T1, P49_T2 (T1 vacía, debe saltarse) y Ljubljana 01 | n2d-standard-4 | AMD Milan | estándar | 0:09:44 | 0:04:44 / 0:04:58 | 2 / 0 | 141.6 | 0.0296 | 0.0296 | correcta |
| 2026-10-17 | local-rc032-negative-controls | Prueba de seguridad: batería de mutaciones RC-032 | ASUS Vivobook M3500QA (portátil) | AMD Zen 3 | equipo propio | 0:50:00 | — / — | — / — | — | 0.0000 | — | correcta |
| 2026-10-18 | flames-extra-a | Colecciones nuevas, bloque A (casos 1 a 90 de 179): HD-BET + FLAMeS 5 modelos | n2d-standard-4 | AMD Milan | estándar | 11:46:50 | 3:28:29 / 8:18:20 | 449 / 0 | 67.5 | 2.0714 | 2.0714 | correcta |
| 2026-10-18 | flames-extra-b | Colecciones nuevas, bloque B (casos 91 a 179): HD-BET + FLAMeS 5 modelos | n2d-standard-4 | AMD Milan | estándar | 10:00:17 | 2:09:06 / 7:51:10 | 443 / 0 | 68.2 | 1.7591 | 1.7591 | correcta |
| 2026-10-18 | lstai-full-a | LST-AI v1.2.0: todo MSLesSeg (P49_T2 saltado) + 30 Ljubljana; controles cuando llegue el permiso de SibBMS | n2-standard-4 | Intel Cascade Lake | estándar | 4:02:49 | 0:05:21 / 3:57:26 | 142 / 0 | 99.6 | 0.8415 | 0.8415 | correcta |
| 2026-10-21 | paperc-oml-full | Artículo C: FLAMeS 5 modelos en las 40 imágenes de Ljubljana con dos visitas (cambios marcados por expertos) | n2d-standard-4 | AMD Milan | estándar | 3:54:19 | 0:02:29 / 3:51:48 | 198 / 0 | 69.0 | 0.6867 | 0.6867 | correcta |
| 2026-10-21 | paperc-oml-pilot | Artículo C, piloto: FLAMeS modelo 0 en Ljubljana con dos visitas (paciente 16) | n2d-standard-4 | AMD Milan | estándar | 0:06:06 | 0:03:38 / 0:02:27 | 2 / 0 | 69.0 | 0.0179 | 0.0179 | correcta |
| 2026-10-21 | toolbench-mindglide-a | Artículo F: MindGlide, brazo principal (misma imagen que FLAMeS), mitad A | n2d-standard-4 | AMD Milan | estándar | 3:33:37 | 0:06:47 / 3:26:49 | 160 / 0 | 84.3 | 0.6504 | 0.6504 | correcta |
| 2026-10-21 | toolbench-mindglide-b | Artículo F: MindGlide, brazo principal (misma imagen que FLAMeS), mitad B | n2-standard-4 | Intel Cascade Lake | estándar | 3:12:56 | 0:07:46 / 3:05:09 | 161 / 0 | 77.2 | 0.6686 | 0.6686 | correcta |
| 2026-10-21 | toolbench-pilot-mindglide | Artículo F, piloto 1 de MindGlide (3 estudios) | e2-standard-4 | Intel Broadwell | estándar | 0:13:27 | 0:07:27 / 0:05:58 | 0 / 3 | — | 0.0331 | 0.0331 | fallida (entorno de software) |
| 2026-10-21 | toolbench-pilot-mindglide-2 | Artículo F, piloto 2 de MindGlide (1 estudio, error completo) | e2-standard-4 | Intel Broadwell | estándar | 0:10:41 | 0:08:25 / 0:02:13 | 0 / 1 | — | 0.0263 | 0.0263 | fallida (entorno de software) |
| 2026-10-21 | toolbench-pilot-mindglide-3 | Artículo F, piloto 3 de MindGlide con permisos corregidos (3 estudios) | n2d-standard-4 | AMD Milan | estándar | 0:12:15 | 0:07:54 / 0:04:18 | 3 / 0 | 84.2 | 0.0373 | 0.0373 | correcta |
| 2026-10-22 | toolbench-mgraw | Artículo F: MindGlide con la imagen original (MS3SEG, Bagdad, PediMS) | e2-standard-4 | Intel Broadwell | estándar | 10:00:01 | 0:08:57 / — | 143 / 3 | 252.8 | 1.4772 | 1.4772 | fallida |
| 2026-10-22 | toolbench-mgraw-2 | Artículo F: MindGlide con la imagen original, casos restantes (36) | e2-standard-4 | Intel Broadwell | estándar | 3:04:22 | 0:08:16 / 2:56:04 | 36 / 0 | 286.1 | 0.4539 | 0.4539 | correcta |

## Rendimiento medido (FLAMeS, un modelo, un caso, sin TTA)

| Corrida | Máquina | Procesador | Mediana s por caso-modelo | USD por caso-modelo (lista) |
|---|---|---|---|---|
| flames-extra-pilot | n2d-standard-4 | AMD Milan | 66.3 | 0.00324 |
| flames-full-a | n2d-standard-4 | AMD Milan | 69.1 | 0.00337 |
| flames-full-b | n2d-standard-4 | AMD Milan | 68.7 | 0.00336 |
| flames-full-c | n2-standard-4 | Intel Cascade Lake | 68.5 | 0.00383 |
| flames-v2-pilot2 | n2-standard-4 | Intel Cascade Lake | 65.5 | 0.00366 |
| lstai-pilot | n2d-standard-4 | AMD Milan | 141.6 | 0.00719 |
| flames-extra-a | n2d-standard-4 | AMD Milan | 67.5 | 0.00330 |
| flames-extra-b | n2d-standard-4 | AMD Milan | 68.2 | 0.00333 |
| lstai-full-a | n2-standard-4 | Intel Cascade Lake | 99.6 | 0.00575 |
| paperc-oml-full | n2d-standard-4 | AMD Milan | 69.0 | 0.00337 |
| paperc-oml-pilot | n2d-standard-4 | AMD Milan | 69.0 | 0.00337 |
| toolbench-mindglide-a | n2d-standard-4 | AMD Milan | 84.3 | 0.00428 |
| toolbench-mindglide-b | n2-standard-4 | Intel Cascade Lake | 77.2 | 0.00446 |
| toolbench-pilot-mindglide-3 | n2d-standard-4 | AMD Milan | 84.2 | 0.00427 |
| toolbench-mgraw | e2-standard-4 | Intel Broadwell | 252.8 | 0.01037 |
| toolbench-mgraw-2 | e2-standard-4 | Intel Broadwell | 286.1 | 0.01174 |

## Computador local

| Fecha | Tarea | Equipo | Duración | Notas |
|---|---|---|---|---|
| 2026-10-17 | Prueba de seguridad: batería de mutaciones RC-032 | ASUS Vivobook M3500QA (portátil) — AMD Ryzen 7 5800H (8 núcleos / 16 hilos) | 0:50:00 | Aproximado (unos 50 min, no cronometrado). Mismo resultado: 3 mutaciones no detectadas por diseño. |

## Notas por corrida

- **flames-pilot**: Encontró 4 fallos de entorno (falta unzip, metadatos, ruta de conda, numpy); se validaron el registro de coste y el borrado automático.
- **flames-pilot2**: Faltaba pip en la imagen del sistema; corregido.
- **flames-pilot3**: Fallo torch/torchvision incompatibles (el mismo que reapareció el 17-10 en flames-v2-pilot).
- **flames-pilot4-gpu**: La tarjeta P4 no fue visible para torch; se pasó a solo procesador.
- **flames-pilot5-cpu**: Cadena validada; se corrigió la orientación de los mapas (transposición 2,1,0).
- **flames-full**: Los mapas de agosto existen, pero el registro de agosto no anotó el tiempo real de esta fila.
- **sibbms-full**: 30 de 40 controles; una máquina Spot fue interrumpida por Google. Las horas de máquina son la suma de las 4.
- **flames-extra-pilot**: Superado: 179 casos descargados una vez y guardados; HD-BET en 2 casos; FLAMeS 3/3 sin errores. Coincidencia con el experto (modelo 0): MS3SEG 0,59 · Bagdad 0,40 · PediMS 0,80.
- **flames-full-a**: Sin errores. Resultado conjunto (725 mapas, 145 por modelo): ver docs/research/records/2026-10-18_flames_5fold_ensemble_check.txt.
- **flames-full-b**: Sin errores. Un caso tardó 156 s (resto 68–72 s).
- **flames-full-c**: No recalculó 6 mapas que ya estaban en el cubo de los pilotos: modelo 0 de Ljubljana 01–04 y modelo 1 de Ljubljana 01–02 (piloto v1, mismo modelo y ajustes; su modelo 0 coincidió con agosto).
- **flames-pilot-1**: Reprodujo los mapas de agosto (mismas lesiones; diferencia máxima 0,002 por redondeo). El guion antiguo no anotaba procesador ni etapas, y su tarifa de 0,08 USD/h era una estimación por debajo del precio real de lista.
- **flames-v2-pilot**: Falló antes del primer caso: torchvision de otra versión de torch. Corregido instalando ambos del mismo origen y con una autoprueba del entorno que para todo antes de gastar.
- **flames-v2-pilot2**: Comparación SUPERADA: mapas idénticos a los de agosto (Dice 1,0; diferencia máxima 0,002 por redondeo). 66 s por caso y modelo con 4 procesadores.
- **lstai-pilot**: Superado: 2 casos en 140 s cada uno, memoria máxima 10,7 GB sin intercambio; P49_T2 saltado (T1 vacía). Mapas en la rejilla de FLAMeS (error de guardado 0,002). La versión de código no se pudo leer en la imagen (sin python ni git); identidad comprobada por huella de la imagen y de los 3 modelos. Comprobación corregida después.
- **flames-extra-a**: 449 mapas sin errores; HD-BET en los casos con cráneo, cada cerebro guardado para reutilizarlo.
- **toolbench-pilot-mindglide**: Fallo en los 3 estudios tras segmentar: solo se guardaba la salida de errores, que escondía la causa real.
- **toolbench-pilot-mindglide-2**: Causa encontrada: MindGlide funciona sin permisos de administrador y no podía escribir en la carpeta de salida.
- **toolbench-pilot-mindglide-3**: Superado: 3/3, unos 84 s por estudio y 5,5 GB de memoria; etiqueta 18 = lesión (documentación oficial).
- **toolbench-mgraw**: Llegó a su tope de 10 h en una máquina E2 lenta (143 hechos, 3 cortados); el resto se terminó en toolbench-mgraw-2.

## Cómo se mide

- **Duración**: reloj de la propia máquina, desde que arranca hasta que se borra sola (`runinfo.json`), con marca de hora por etapa: preparación del entorno, pesos del modelo, datos, lista de casos, cálculo y final.
- **Procesador**: el que Google asigna (`cpuPlatform`) y el modelo que ve el sistema (`lscpu`). Las corridas de agosto no lo registraron.
- **Coste**: segundos × precio de lista por hora (núcleos + memoria + disco de arranque con su tamaño real, 50 o 100 GB, según el precio guardado al lanzar cada máquina). No incluye almacenamiento ni red, que van en su propia línea. La red de entrada es gratis y los datos no salen de la región.
- **Agosto**: copiado tal cual de `docs/calm-ms/cost-ledger.csv`; allí la tarifa era una estimación, por eso se recalcula también a precio de lista. Las horas de máquina se derivan de coste ÷ tarifa registrados.
- **Comprobación**: cada mapa lleva su huella SHA-256 de entrada y de pesos en el manifiesto de la corrida; el piloto 2 reprodujo los mapas de agosto (mismas lesiones, diferencia máx. 0,002 por redondeo).

