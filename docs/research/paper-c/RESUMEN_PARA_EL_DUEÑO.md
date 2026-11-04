# Artículo C — resumen para el dueño (31-10-2026)

## De qué trata, en una frase

Cuando la aplicación compara dos resonancias de un paciente con esclerosis múltiple, propone
"lesiones nuevas". El artículo C estudia si podemos **garantizar con números** cuántas veces ese
aviso es falso en un paciente que en realidad está estable — por ejemplo, "como mucho 1 de cada 10" —
y cuánto se pierde a cambio.

## Qué está listo (todo guardado en GitHub, propuesta de cambios n.º 60, sin unir a la copia principal)

| Archivo | Qué es |
|---|---|
| `manuscript/manuscript.md` | El artículo completo en borrador: introducción, trabajos previos con 44 referencias comprobadas una a una, métodos, el plan del estudio principal y los resultados del piloto. Lo que depende de los datos nuevos está marcado "TODO". |
| `PREREGISTRATION_C.md` | El plan del estudio principal, escrito **antes** de ver los datos, listo para publicarlo en OSF (una web donde los investigadores dejan su plan con fecha, para demostrar que no lo cambiaron después). |
| `MSSEG2_ACCESS_REQUEST.md` | Cómo pedir los datos, qué dice el acuerdo de uso, el correo ya escrito en inglés y francés, y **tu lista de pasos (§8)**. |
| `APP_FEATURE_SPEC.md` | Cómo se convierte el artículo en una función de la aplicación, y qué hay que validar antes. |
| `research/paper_c/stage0_score_v2.py`, `power_msseg2.py` | Dos cálculos nuevos hechos solo con los datos del piloto (ver abajo). |

## Lo que descubrimos hoy y cambia los planes

1. **Con la cuenta pública solo llegan 40 pacientes, de ellos unos 11 estables**, no 28 como decían
   nuestras notas. Los 28 estables eran del grupo de prueba del concurso, que no se reparte. El
   correo que vas a enviar pide permiso para usar esos 60 pacientes; si dicen que no, el estudio se
   hace con los 40, como ya está previsto en el plan.
2. **El acuerdo prohíbe el uso comercial** de los datos y de cualquier cosa calculada con ellos.
   Por eso: el artículo sí, pero ningún número calculado con MSSEG-2 puede ir dentro de la
   aplicación. El correo lo dice claramente, y también que tú desarrollas un producto comercial —
   mejor decirlo antes que tener problemas después.
3. **Probamos una puntuación "más lista"** (que combina tres medidas) y **no mejora** a la sencilla
   que ya usa la aplicación. Se queda la sencilla. Es un resultado honesto y va en el artículo.
4. **Probabilidad de que el estudio salga bien** (calculada con el piloto): si los datos franceses se
   parecen al caso bueno del piloto, el estudio demostrará la utilidad con casi total seguridad
   (99 %); si se parecen al caso malo (equipos distintos entre visitas), solo con un 50 %. Con los
   60 pacientes extra, sube a entre el 73 % y el 100 % según el caso. Por eso merece la pena pedirlos.
5. Corregimos dos errores de nuestras propias notas: el autor principal del conjunto de datos
   MSLesSeg es Guarnera (no Rondinella), y un dato sobre otros programas del concurso estaba mal
   resumido. Ninguno cambia un resultado.

## Lo que tienes que hacer tú (una sola cosa)

**Pedir los datos**: rellenar un formulario de 4 casillas y enviar un correo ya escrito. Los pasos
exactos, en español, están en `MSSEG2_ACCESS_REQUEST.md`, apartado 8. Necesitas un correo
profesional a tu nombre (por ejemplo `tunombre@mstool-ai.com`); Gmail no vale según el acuerdo.

## Lo que hago yo después (no necesitas hacer nada)

Cuando me digas que tienes acceso: publicar el plan en OSF antes de abrir los datos, descargar,
preparar las imágenes, pasar FLAMeS (en el ordenador o en el proyecto de investigación de la nube,
nunca en producción), hacer el análisis tal como está escrito y rellenar el artículo. Solo se
guardan resultados de grupo, nunca datos de un paciente concreto.

## Cómo llega a la aplicación (confirmado)

Función: **"garantía de candidatas longitudinales"**. Dentro de las lesiones nuevas que la aplicación
ya enseña como candidatas sin confirmar, marcaría las que superan un umbral con garantía ("en
pacientes estables, este aviso aparece por error como mucho en el 10 %"), o diría "sin garantía para
estas imágenes". **No se puede construir todavía**: antes hay que (1) tener el resultado del estudio
principal, (2) repetirlo con datos de un hospital en condiciones reales, con al menos 30 pacientes
estables y un modelo de segmentación que sí se pueda vender (FLAMeS tampoco permite uso comercial),
y (3) pasar el proceso de seguridad de la aplicación (requisito, análisis de riesgos, revisión,
pruebas y tu aprobación).
