"""Todo lo que habla con YouTube pasa por yt-dlp: leer feeds, buscar, bajar y marcar como visto.

Leer un feed con extract_flat solo baja una página de metadatos (títulos, canal, duración),
sin abrir cada video ni usar un navegador: es la forma más barata de saber qué te recomienda YouTube.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from yt_dlp import YoutubeDL

from .config import Config

log = logging.getLogger(__name__)

FEEDS = {
    "recomendados": ":ytrec",
    "suscripciones": ":ytsubs",
    "historial": ":ythistory",
}


def _url(vid: str) -> str:
    return f"https://www.youtube.com/watch?v={vid}"


def _opciones_base(cfg: Config) -> dict:
    opts: dict = {"quiet": True, "no_warnings": True, "noprogress": True}
    if cfg.cookies:
        opts["cookiefile"] = str(cfg.cookies)
    # YouTube exige resolver un reto de JavaScript; yt-dlp usa el primer runtime que encuentre.
    runtimes = {nombre: {} for nombre in ("deno", "node", "bun", "quickjs") if shutil.which(nombre)}
    if runtimes:
        opts["js_runtimes"] = runtimes
    return opts


def _a_candidato(entrada: dict, fuente: str) -> dict | None:
    vid = entrada.get("id")
    if not vid or entrada.get("ie_key") not in (None, "Youtube"):
        return None
    if "/shorts/" in (entrada.get("url") or ""):
        return None
    return {
        "id": vid,
        "titulo": entrada.get("title") or vid,
        "canal": entrada.get("channel") or entrada.get("uploader"),
        "duracion": int(entrada["duration"]) if entrada.get("duration") else None,
        "fuente": fuente,
    }


def _listar(cfg: Config, url: str, fuente: str, limite: int) -> list[dict]:
    opts = _opciones_base(cfg) | {"extract_flat": "in_playlist", "playlistend": limite}
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:  # yt-dlp lanza muchos tipos distintos
        log.warning("No pude leer %s: %s", fuente, e)
        return []
    candidatos = (_a_candidato(e, fuente) for e in (info or {}).get("entries") or [])
    return [c for c in candidatos if c]


def leer_feeds(cfg: Config) -> list[dict]:
    resultado: list[dict] = []
    for fuente in cfg.fuentes:
        if fuente not in FEEDS:
            log.warning("Fuente desconocida: %s (usa %s)", fuente, ", ".join(FEEDS))
            continue
        if not cfg.cookies:
            log.warning("La fuente '%s' necesita cookies de tu cuenta; la salto.", fuente)
            continue
        resultado += _listar(cfg, FEEDS[fuente], fuente, cfg.por_fuente)
    for canal in cfg.canales:
        url = canal.rstrip("/") + "/videos" if "/@" in canal and not canal.endswith("/videos") else canal
        resultado += _listar(cfg, url, "canal", 10)
    return resultado


def buscar(cfg: Config, consulta: str, cuantos: int = 6) -> list[dict]:
    return _listar(cfg, f"ytsearch{cuantos}:{consulta}", "búsqueda", cuantos)


def bajar(cfg: Config, vid: str, al_progresar=None) -> tuple[Path, Path | None]:
    """Baja el video en MP4 (H.264, lo que cualquier tele decodifica por hardware).

    Devuelve (archivo de video, miniatura o None).
    """
    destino = cfg.carpeta_videos
    destino.mkdir(parents=True, exist_ok=True)
    h = cfg.calidad_max
    opts = _opciones_base(cfg) | {
        "format": (
            f"bv*[height<={h}][vcodec^=avc1]+ba[ext=m4a]/"
            f"b[height<={h}][ext=mp4]/bv*[height<={h}]+ba/b"
        ),
        "merge_output_format": "mp4",
        "outtmpl": {"default": str(destino / "%(id)s.%(ext)s")},
        "writethumbnail": True,
        "postprocessors": [{"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"}],
        "concurrent_fragment_downloads": 4,
        "retries": 5,
        "noplaylist": True,
        "mark_watched": cfg.marcar_visto == "al_bajar",
    }
    if al_progresar:
        opts["progress_hooks"] = [al_progresar]
    with YoutubeDL(opts) as ydl:
        ydl.extract_info(_url(vid), download=True)

    video = destino / f"{vid}.mp4"
    if not video.exists():
        otros = sorted(p for p in destino.glob(f"{vid}.*") if p.suffix not in (".jpg", ".part", ".ytdl"))
        if not otros:
            raise FileNotFoundError(f"yt-dlp terminó pero no encuentro el archivo de {vid}")
        video = otros[0]
    miniatura = destino / f"{vid}.jpg"
    return video, (miniatura if miniatura.exists() else None)


def marcar_visto(cfg: Config, vid: str) -> None:
    """Le dice a YouTube que viste el video, para que te recomiende cosas parecidas."""
    if not cfg.cookies:
        return
    opts = _opciones_base(cfg) | {"mark_watched": True, "skip_download": True}
    try:
        with YoutubeDL(opts) as ydl:
            ydl.extract_info(_url(vid), download=False)
    except Exception as e:
        log.warning("No pude marcar %s como visto en YouTube: %s", vid, e)
