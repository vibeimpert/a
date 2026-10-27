#!/usr/bin/env bash
# Instala `gem` y la integración con Claude Code a nivel de usuario.
#   ./install.sh              → gem + skill + reglas en ~/.claude/CLAUDE.md + permiso Bash(gem:*)
#   ./install.sh --with-hook  → además, el hook que bloquea leer archivos grandes completos
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
with_hook=0; [[ ${1:-} == --with-hook ]] && with_hook=1

command -v node >/dev/null || { echo "Necesitas Node.js 20+"; exit 1; }
if ! command -v gemini >/dev/null; then
  echo "→ Instalando Gemini CLI"; npm install -g @google/gemini-cli
fi

mkdir -p "$BIN_DIR" "$CLAUDE_DIR/skills" "$CLAUDE_DIR/hooks"
ln -sf "$ROOT/bin/gem" "$BIN_DIR/gem"
rm -rf "$CLAUDE_DIR/skills/gemini"; cp -r "$ROOT/claude/skills/gemini" "$CLAUDE_DIR/skills/gemini"
echo "→ gem en $BIN_DIR/gem; skill en $CLAUDE_DIR/skills/gemini"

touch "$CLAUDE_DIR/CLAUDE.md"
if ! grep -q "Delegación a Gemini" "$CLAUDE_DIR/CLAUDE.md"; then
  printf '\n' >>"$CLAUDE_DIR/CLAUDE.md"; cat "$ROOT/claude/CLAUDE.snippet.md" >>"$CLAUDE_DIR/CLAUDE.md"
  echo "→ reglas añadidas a $CLAUDE_DIR/CLAUDE.md"
fi

if ((with_hook)); then
  cp "$ROOT/claude/hooks/guard-large-read.sh" "$CLAUDE_DIR/hooks/"
fi

# Fusiona permisos (y hook opcional) en settings.json sin pisar lo existente.
node - "$CLAUDE_DIR/settings.json" "$with_hook" "$CLAUDE_DIR/hooks/guard-large-read.sh" <<'EOF'
const fs = require("fs");
const [file, withHook, hookPath] = process.argv.slice(2);
const s = fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, "utf8")) : {};
s.permissions ??= {}; s.permissions.allow ??= [];
if (!s.permissions.allow.includes("Bash(gem:*)")) s.permissions.allow.push("Bash(gem:*)");
if (withHook === "1") {
  s.hooks ??= {}; s.hooks.PreToolUse ??= [];
  const already = JSON.stringify(s.hooks.PreToolUse).includes("guard-large-read.sh");
  if (!already) s.hooks.PreToolUse.push({ matcher: "Read", hooks: [{ type: "command", command: hookPath }] });
}
fs.writeFileSync(file, JSON.stringify(s, null, 2) + "\n");
console.log("→ settings actualizados en " + file);
EOF

case ":$PATH:" in *":$BIN_DIR:"*) ;; *) echo "⚠ Añade $BIN_DIR a tu PATH";; esac
echo
echo "Último paso (una sola vez): ejecuta 'gemini', elige 'Login with Google' y sal con /quit."
echo "Prueba: gem -m flash \"di hola en 3 palabras\""
