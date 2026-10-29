"""Elige qué bajar. Una sola llamada a Claude por ciclo con una lista compacta de títulos.

Para ahorrar tokens:
  * Claude no navega ni abre videos: solo lee una línea por candidato (título, canal, duración).
  * Los candidatos se numeran y Claude responde números, no IDs ni títulos.
  * La respuesta es JSON con esquema fijo (structured outputs), sin texto de relleno.
Si no hay API key, se usa un filtro simple basado en los canales que ya terminaste de ver.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from .config import Config

log = logging.getLogger(__name__)

SISTEMA = """Eres el programador de un canal de TV personal. Recibes lo que la persona vio \
últimamente y una lista numerada de videos candidatos de YouTube. Elige los que más probablemente \
quiera ver, con variedad (no todos del mismo canal ni del mismo tema). Evita clickbait, \
reacciones, recopilaciones de relleno y temas que haya saltado o marcado con "no me gusta". \
Propón también búsquedas cortas de YouTube para descubrir cosas nuevas que le gustarían. \
El "motivo" es una frase breve en español que se muestra en la tele."""

ESQUEMA = {
    "type": "object",
    "properties": {
        "elegidos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"n": {"type": "integer"}, "motivo": {"type": "string"}},
                "required": ["n", "motivo"],
                "additionalProperties": False,
            },
        },
        "busquedas": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["elegidos", "busquedas"],
    "additionalProperties": False,
}


@dataclass
class Decision:
    elegidos: list[tuple[dict, str]] = field(default_factory=list)  # (candidato, motivo)
    busquedas: list[str] = field(default_factory=list)


def _duracion(seg: int | None) -> str:
    if not seg:
        return "?"
    return f"{seg // 3600}h{seg % 3600 // 60:02d}" if seg >= 3600 else f"{seg // 60}m"


def _linea_historial(h: dict) -> str:
    if h["opinion"] == "me_gusta":
        marca = "♥"
    elif h["opinion"] == "no_me_gusta":
        marca = "✗"
    elif h["duracion"] and h["posicion"] < 0.3 * h["duracion"] and h["estado"] != "visto":
        marca = "saltado"
    else:
        marca = "visto"
    return f"[{marca}] {h['titulo']} — {h['canal'] or '?'}"


def armar_prompt(cfg: Config, historial: list[dict], candidatos: list[dict], cuantos: int) -> str:
    partes = []
    if cfg.gustos.strip():
        partes.append(f"Gustos declarados: {cfg.gustos.strip()}")
    if historial:
        partes.append("Visto últimamente:\n" + "\n".join(_linea_historial(h) for h in historial))
    lineas = [
        f"{i}|{c['titulo']}|{c['canal'] or '?'}|{_duracion(c['duracion'])}"
        for i, c in enumerate(candidatos)
    ]
    partes.append("Candidatos (n|título|canal|duración):\n" + "\n".join(lineas))
    partes.append(
        f"Elige hasta {cuantos} y propone {cfg.busquedas_extra} búsquedas nuevas."
    )
    return "\n\n".join(partes)


def _por_reglas(historial: list[dict], candidatos: list[dict], cuantos: int) -> Decision:
    gustan = {h["canal"] for h in historial if h["opinion"] == "me_gusta" or h["estado"] == "visto"}
    no_gustan = {h["canal"] for h in historial if h["opinion"] == "no_me_gusta"}
    orden_fuente = {"recomendados": 0, "suscripciones": 1, "canal": 1, "búsqueda": 2}

    def puntaje(c: dict) -> tuple:
        return (c["canal"] not in gustan, orden_fuente.get(c["fuente"], 3))

    elegibles = sorted((c for c in candidatos if c["canal"] not in no_gustan), key=puntaje)
    elegidos, por_canal = [], {}
    for c in elegibles:
        if por_canal.get(c["canal"], 0) >= 2:
            continue
        por_canal[c["canal"]] = por_canal.get(c["canal"], 0) + 1
        motivo = "De un canal que ya viste" if c["canal"] in gustan else f"De tus {c['fuente']}"
        elegidos.append((c, motivo))
        if len(elegidos) == cuantos:
            break
    return Decision(elegidos=elegidos)


def _con_claude(cfg: Config, prompt: str, candidatos: list[dict], cuantos: int, cliente=None) -> Decision:
    import anthropic

    cliente = cliente or anthropic.Anthropic()
    respuesta = cliente.beta.messages.create(
        model=cfg.modelo,
        max_tokens=4096,
        system=SISTEMA,
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": cfg.esfuerzo, "format": {"type": "json_schema", "schema": ESQUEMA}},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if respuesta.stop_reason == "refusal":
        raise RuntimeError("Claude no quiso elegir esta vez")
    if respuesta.stop_reason == "max_tokens":
        raise RuntimeError("La respuesta de Claude quedó cortada")
    texto = next(b.text for b in respuesta.content if b.type == "text")
    datos = json.loads(texto)
    log.info(
        "Claude: %s tokens de entrada, %s de salida",
        respuesta.usage.input_tokens, respuesta.usage.output_tokens,
    )

    decision = Decision(busquedas=[b.strip() for b in datos["busquedas"] if b.strip()][: cfg.busquedas_extra])
    vistos = set()
    for e in datos["elegidos"]:
        n = e["n"]
        if 0 <= n < len(candidatos) and n not in vistos:
            vistos.add(n)
            decision.elegidos.append((candidatos[n], e["motivo"]))
    decision.elegidos = decision.elegidos[:cuantos]
    return decision


def elegir(cfg: Config, historial: list[dict], candidatos: list[dict], cuantos: int, cliente=None) -> Decision:
    if not candidatos or cuantos <= 0:
        return Decision()
    if cfg.usar_claude or cliente is not None:
        try:
            prompt = armar_prompt(cfg, historial, candidatos, cuantos)
            return _con_claude(cfg, prompt, candidatos, cuantos, cliente)
        except Exception as e:
            log.warning("Falló la elección con Claude (%s); uso reglas simples.", e)
    return _por_reglas(historial, candidatos, cuantos)
