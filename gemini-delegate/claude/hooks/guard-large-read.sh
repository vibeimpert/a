#!/usr/bin/env bash
# PreToolUse(Read): bloquea leer archivos de texto grandes completos y sugiere `gem`.
# Permite la lectura si se pasa offset/limit. Umbral: GEM_READ_MAX_LINES (por defecto 400).
input="$(cat)"
read -r has_range path < <(node -e '
  const t = JSON.parse(require("fs").readFileSync(0, "utf8")).tool_input || {};
  console.log((t.offset != null || t.limit != null ? 1 : 0) + " " + (t.file_path || ""));' <<<"$input")
[[ -f $path && $has_range == 0 ]] || exit 0
case "$path" in *.png|*.jpg|*.jpeg|*.gif|*.webp|*.pdf|*.ipynb) exit 0 ;; esac
lines=$(wc -l <"$path")
max=${GEM_READ_MAX_LINES:-400}
if ((lines > max)); then
  echo "Archivo de $lines líneas. Para ahorrar tokens: 'gem -t summarize -f $path \"<qué necesitas>\"' o 'gem -t find', y luego Read con offset/limit en las líneas citadas." >&2
  exit 2
fi
exit 0
