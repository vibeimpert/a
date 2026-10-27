## Delegación a Gemini (ahorro de tokens)

- Gemini lee, Claude decide. Antes de leer >300 líneas, explorar un repo, analizar logs o buscar en la web, usa la skill `gemini` (`gem`).
- Junta varias preguntas sobre el mismo material en una sola llamada a `gem`.
- Tras `gem`, lee solo los rangos `ruta:línea` citados con `Read` offset/limit.
- No envíes a Gemini secretos (.env, llaves, credenciales).
- Respuestas de Claude: cortas, sin repetir código que ya está en archivos; muestra diffs, no archivos completos.
