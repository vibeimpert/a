"""Carga la configuración (config.toml) con valores por defecto razonables."""
from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    # [servidor]
    puerto: int = 8765
    carpeta: Path = Path("./datos")

    # [espacio]
    max_gb: float = 20.0
    videos_listos: int = 12
    borrar_vistos_tras_horas: float = 2.0
    borrar_sin_ver_tras_dias: float = 7.0

    # [youtube]
    cookies: Path | None = None
    fuentes: list[str] = field(default_factory=lambda: ["recomendados", "suscripciones"])
    canales: list[str] = field(default_factory=list)
    busquedas: list[str] = field(default_factory=list)
    por_fuente: int = 40
    calidad_max: int = 1080
    marcar_visto: str = "al_ver"  # al_ver | al_bajar | nunca
    duracion_min_seg: int = 120
    duracion_max_seg: int = 5400
    cada_minutos: int = 60

    # [claude]
    claude_activado: bool = True
    modelo: str = "claude-opus-5-5"
    esfuerzo: str = "low"
    gustos: str = ""
    busquedas_extra: int = 3

    @property
    def carpeta_videos(self) -> Path:
        return self.carpeta / "videos"

    @property
    def base_datos(self) -> Path:
        return self.carpeta / "yotv.db"

    @property
    def max_bytes(self) -> int:
        return int(self.max_gb * 1024**3)

    @property
    def usar_claude(self) -> bool:
        return self.claude_activado and bool(
            os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        )


_SECCIONES = {
    "servidor": {"puerto", "carpeta"},
    "espacio": {"max_gb", "videos_listos", "borrar_vistos_tras_horas", "borrar_sin_ver_tras_dias"},
    "youtube": {
        "cookies", "fuentes", "canales", "busquedas", "por_fuente", "calidad_max", "marcar_visto",
        "duracion_min_seg", "duracion_max_seg", "cada_minutos",
    },
    "claude": {"activado", "modelo", "esfuerzo", "gustos", "busquedas_extra", "api_key"},
}


def cargar(ruta: str | Path | None) -> Config:
    cfg = Config()
    if ruta is None:
        return cfg
    ruta = Path(ruta)
    with open(ruta, "rb") as f:
        datos = tomllib.load(f)
    base = ruta.parent

    for seccion, claves in _SECCIONES.items():
        for clave, valor in datos.get(seccion, {}).items():
            if clave not in claves:
                raise ValueError(f"Opción desconocida en [{seccion}]: {clave}")
            if seccion == "claude" and clave == "api_key":
                if valor:
                    os.environ.setdefault("ANTHROPIC_API_KEY", valor)
                continue
            nombre = "claude_activado" if (seccion, clave) == ("claude", "activado") else clave
            if nombre in ("carpeta", "cookies"):
                valor = (base / valor).resolve() if valor else None
            setattr(cfg, nombre, valor)

    if cfg.marcar_visto not in ("al_ver", "al_bajar", "nunca"):
        raise ValueError("marcar_visto debe ser al_ver, al_bajar o nunca")
    if cfg.cookies is not None and not cfg.cookies.exists():
        logging.getLogger(__name__).warning(
            "No encuentro %s: sigo sin tu cuenta (solo canales y búsquedas).", cfg.cookies
        )
        cfg.cookies = None
    return cfg
