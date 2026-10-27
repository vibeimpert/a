---
name: gemini
description: Delega a Gemini (vía el comando `gem`) el trabajo que consume muchos tokens de lectura — explorar un repo, leer archivos o logs grandes, buscar dónde está algo, revisar un diff, investigar en la web, redactar borradores — y recibe solo un resumen corto con citas ruta:línea. Úsala antes de leer más de ~300 líneas, antes de explorar un repo desconocido, y para cualquier búsqueda web.
---

# Delegar a Gemini con `gem`

Gemini tiene ~1M de contexto y una cuota gratuita medida en **peticiones**, no en tokens.
Tú (Claude) pagas por cada token que entra en tu contexto. Regla: **Gemini lee, tú decides.**

## Cuándo delegar (sí)

| Situación | Comando |
|---|---|
| Repo o carpeta desconocida | `gem -t map -d . "objetivo: <lo que vas a hacer>"` |
| ¿Dónde está X? | `gem -t find -d . "<qué buscas>"` |
| Archivo > 300 líneas | `gem -t summarize -f ruta "<qué necesitas saber>"` |
| Logs / salida de tests larga | `cmd 2>&1 \| gem -t logs -f - "<contexto>"` |
| Revisar cambios | `git diff main... \| gem -t review -f - "<foco>"` |
| Docs de librería / web | `gem -t research "<pregunta precisa con versión>"` |
| Borrador grande (tests, docs) | `gem -t draft -w -d . "<qué y dónde>"` y luego `git diff --stat` |

## Cuándo NO delegar

- Archivos < 300 líneas que vas a editar: léelos tú (necesitas el texto exacto para Edit).
- Decisiones de diseño finales, cambios delicados, o cuando Gemini ya falló dos veces en lo mismo.
- Datos secretos o código que el usuario no quiere enviar a Google.

## Reglas para ahorrar tokens

1. **Una petición gorda > muchas flacas**: junta todas las preguntas sobre el mismo material en una sola llamada (numéradas). La cuota cuenta peticiones.
2. **Pide solo lo accionable**: di para qué lo necesitas ("voy a añadir un endpoint") para que filtre.
3. **Sigue con lecturas quirúrgicas**: usa las citas `ruta:línea` con `Read` + `offset`/`limit`, no el archivo entero.
4. **Ajusta el tamaño**: `-n 120` para respuestas cortas; `-o archivo` cuando el resultado sea un artefacto que no necesitas leer entero.
5. **Verifica lo crítico**: Gemini puede equivocarse; antes de editar, confirma la línea citada.
6. **Modelo**: `-m flash` para mecánico (buscar, resumir, logs); `pro` (por defecto) para razonar, revisar, mapear.
7. **Caché**: repetir la misma pregunta sobre el mismo contenido no gasta petición. Usa `--fresh` solo si cambió algo que la caché no ve.
8. Si `gem` falla por autenticación, dile al usuario que ejecute `gemini` una vez y elija "Login with Google"; no reintentes en bucle.

`gem --stats` muestra cuántos tokens leyó Gemini en lugar de ti.
