# gemini-delegate — Claude decide, Gemini lee

Un sistema para que Claude Code delegue a Gemini el trabajo que más tokens consume
(leer, explorar, buscar, investigar, resumir) **sin API key**, usando Gemini CLI con
tu cuenta de Google, y recibir solo respuestas cortas con citas `ruta:línea`.

```
          ┌──────────────── Claude Code (caro por token) ────────────────┐
          │  planifica · decide · edita con precisión · verifica          │
          └──────┬──────────────────────────────────────────▲────────────┘
     instrucción │  skill "gemini" + reglas en CLAUDE.md     │ ≤250 palabras
     + rutas     ▼                                           │ + ruta:línea
          ┌──────────────────── gem (wrapper) ───────────────┴────────────┐
          │ plantilla de tarea + contrato de salida · caché por contenido │
          │ fallback pro→flash→flash-lite si se agota la cuota            │
          │ tope de caracteres devueltos · registro de uso (--stats)      │
          └──────┬────────────────────────────────────────────────────────┘
                 ▼  gemini -p … -o json   (headless, solo lectura por defecto)
          ┌──────────── Gemini CLI · Login with Google (sin API key) ─────┐
          │ ~1M de contexto · lee archivos · grep · búsqueda web · fetch  │
          └───────────────────────────────────────────────────────────────┘
```

## Por qué funciona

| | Claude | Gemini CLI (cuenta personal de Google) |
|---|---|---|
| Qué cuesta | cada token que entra en su contexto | **peticiones** por minuto/día, no tokens |
| Contexto | se llena y se compacta | ~1M de tokens por petición |
| En qué es mejor aquí | razonamiento fino, edición exacta | leer muchísimo y resumir |

La conclusión es asimétrica: **en Gemini sale gratis meter contexto gigante, lo que se raciona
es el número de llamadas**. Por eso el sistema hace *pocas peticiones muy gordas* a Gemini
y le devuelve a Claude solo el destilado.

> Las cuotas gratuitas cambian. Históricamente: ~60 peticiones/min y ~1000/día con login de
> Google. Consulta las vigentes con `/stats` dentro de `gemini` o en la documentación oficial.

### ¿Por qué Gemini CLI y no "la web de Gemini"?

"Sin API" aquí significa **sin API key**: Gemini CLI se autentica con OAuth de tu cuenta de
Google (nivel gratuito para individuos). Automatizar gemini.google.com con scraping o un
navegador va contra sus términos, se rompe con cada cambio de la web y no da conteo de
tokens. La CLI es oficial, estable, tiene modo headless con salida JSON y herramientas
propias (leer archivos, grep, búsqueda web).

**Privacidad:** en el nivel gratuito Google puede usar prompts y código para mejorar sus
productos (revisa y ajusta con `/privacy` en `gemini`). No delegues secretos ni código que
no puedas compartir.

## Instalación

```bash
cd gemini-delegate
./install.sh              # gem + skill + reglas + permiso Bash(gem:*)
./install.sh --with-hook  # además, bloquea Read de archivos >400 líneas sin offset/limit
gemini                    # una sola vez: "Login with Google", luego /quit
gem -m flash "di hola en 3 palabras"
```

Qué instala:
- `~/.local/bin/gem` → `bin/gem`
- `~/.claude/skills/gemini/SKILL.md` — le enseña a Claude cuándo y cómo delegar
- un bloque en `~/.claude/CLAUDE.md` con las reglas de delegación
- `Bash(gem:*)` en `~/.claude/settings.json` para que no pida permiso cada vez
- (opcional) hook `PreToolUse` sobre `Read` que redirige lecturas gigantes a `gem`

## Uso de `gem`

```bash
gem -t map -d . "objetivo: añadir autenticación OAuth"           # mapa de un repo
gem -t find -d . "dónde se validan los tokens JWT"                # localizar código
gem -t summarize -f docs/spec.md "requisitos del endpoint /pagos" # leer un archivo grande
npm test 2>&1 | gem -t logs -f - "tests de pagos"                 # diagnosticar salida larga
git diff main... | gem -t review -f - "seguridad y casos borde"    # revisar un diff
gem -t research "breaking changes de pydantic 2.x a 3.x"          # investigar en la web
gem -t draft -w -d . "tests unitarios para src/pagos.py en tests/" # Gemini escribe archivos
gem --stats                                                       # tokens que Claude no leyó
```

| Opción | Efecto |
|---|---|
| `-t TAREA` | plantilla de `prompts/` (map, find, summarize, review, research, logs, draft) |
| `-f RUTA` | adjunta un archivo con números de línea (repetible; `-` = stdin) |
| `-d DIR` | Gemini explora `DIR` con sus herramientas |
| `-m` | `pro`, `flash`, `flash-lite`, `auto` o nombre exacto. Por defecto `flash` para find/summarize/logs y `pro` para el resto |
| `-n N` | límite de palabras (por defecto 250) |
| `-w` | permite editar archivos (`--approval-mode auto_edit`); sin `-w` no puede escribir ni ejecutar shell |
| `-o F` | guarda la respuesta en `F` e imprime solo la ruta |
| `--fresh` | ignora la caché |

Variables: `GEM_TIMEOUT` (600 s), `GEM_MAX_CHARS` (6000), `GEM_CACHE_TTL` (86400 s),
`GEM_FALLBACK` (`"pro flash flash-lite"`), `GEM_EXTRA_ARGS`, `GEM_BIN`.

### Qué hace `gem` por dentro

1. **Plantilla + contrato**: cada tarea tiene un prompt especializado y todas comparten
   `prompts/_contract.md` (límite de palabras, citar `ruta:línea` en vez de pegar código,
   "NO ENCONTRADO" en vez de inventar).
2. **Contexto numerado**: los archivos adjuntos van con números de línea para que las citas
   sean exactas y Claude pueda hacer `Read` con `offset/limit`.
3. **Caché por contenido**: la clave incluye modelo, prompt, contenido de los archivos y,
   con `-d`, el `HEAD` y el `git status` del repo. Repetir una pregunta no gasta cuota.
4. **Solo lectura por defecto**: en modo headless Gemini CLI rechaza las herramientas que
   requieren confirmación (escribir, shell). `-w` habilita solo ediciones.
5. **Fallback por cuota**: ante 429/`RESOURCE_EXHAUSTED` baja `pro → flash → flash-lite`
   y avisa por stderr. Otros errores se reportan sin reintentar.
6. **Tope de salida**: si la respuesta excede `GEM_MAX_CHARS`, Claude recibe el inicio y la
   ruta del texto completo.
7. **Métricas**: `~/.cache/gem/usage.jsonl` registra tokens de entrada de Gemini y tamaño
   devuelto; `gem --stats` estima el ahorro.

## Exprimir Gemini al máximo

- **Peticiones gordas**: junta todas las preguntas sobre el mismo material en una llamada
  numerada: `gem -t summarize -f a.md -f b.md "1) … 2) … 3) …"`. 1 petición en lugar de 3.
- **Dale el repo entero**: con `-d .` explora libremente; su contexto aguanta repos medianos
  completos. Para monorepos, apunta a la subcarpeta.
- **Web gratis**: toda investigación de documentación, versiones o errores va con
  `-t research` (búsqueda de Google integrada) en vez de que Claude haga WebSearch/WebFetch.
- **Flash para lo mecánico**: localizar, resumir, logs → `flash` (más cuota, más rápido).
  `pro` para revisar, mapear y razonar.
- **Borradores voluminosos**: tests, docstrings, migraciones repetitivas, traducciones →
  `-t draft -w`; Claude solo revisa `git diff --stat` y los puntos delicados.
- **Segunda opinión barata**: `git diff | gem -t review -f -` antes de dar algo por terminado.

## Optimizar tokens de Claude (más allá de delegar)

1. **No leas, pregunta**: archivo >300 líneas → `gem`, luego `Read` solo del rango citado.
2. **Contexto en disco, no en el chat**: resultados largos con `gem -o archivo`; Claude lee
   solo lo que necesita.
3. **Salida de comandos filtrada**: `cmd 2>&1 | tail -50`, `grep -c`, `--quiet`; o
   `| gem -t logs -f -` si es larga.
4. **CLAUDE.md corto**: se carga en cada turno; cada línea cuesta en todas las peticiones.
   Mueve lo detallado a skills (se cargan solo cuando aplican).
5. **Sesiones enfocadas**: una tarea por sesión; `/clear` al cambiar de tema y `/compact`
   cuando el contexto crece. Usa `/context` y `/cost` para ver qué consume.
6. **Respuestas compactas**: pide diffs y resúmenes, no archivos completos re-impresos.
7. **Subagentes con criterio**: cada subagente arranca en frío y vuelve a leer; para
   exploración pura, `gem` es más barato que un subagente de Claude.
8. **Modelo adecuado**: tareas simples de Claude con un modelo más pequeño; el grande solo
   para lo que lo necesita.

## Límites honestos

- Gemini puede alucinar rutas o líneas: Claude debe verificar antes de editar.
- La cuota gratuita y los nombres de modelos cambian; `-m` acepta alias (`pro`, `flash`,
  `flash-lite`, `auto`) que la CLI resuelve al modelo vigente.
- Delegar añade latencia (segundos a un par de minutos por llamada).
- La caché no detecta cambios fuera de git cuando usas `-d` en un directorio sin repo:
  usa `--fresh` en ese caso.

## Estructura

```
gemini-delegate/
├── bin/gem                         wrapper (bash + node)
├── prompts/_contract.md            contrato de salida común
├── prompts/{map,find,summarize,review,research,logs,draft}.md
├── claude/skills/gemini/SKILL.md   skill para Claude Code
├── claude/CLAUDE.snippet.md        reglas que se añaden a ~/.claude/CLAUDE.md
├── claude/hooks/guard-large-read.sh hook opcional anti-lecturas gigantes
└── install.sh
```
