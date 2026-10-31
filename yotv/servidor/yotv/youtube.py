"""Todo lo que habla con YouTube pasa por yt-dlp: leer feeds, buscar, bajar y marcar como visto.

Leer un feed con extract_flat solo baja una página de metadatos (títulos, canal, duración),
sin abrir cada video ni usar un navegador: es la forma más barata de saber qué te recomienda YouTube.
"""
from __future__ import annotations

import logging
import shutil
import threading
from dataclasses import dataclass, field
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


@dataclass
class Pista:
    """Un archivo que se está bajando (video o audio). El servidor lo lee mientras crece."""
    ruta: Path
    total: int | None = None  # tamaño final exacto; sin él no se puede ver hasta que termine
    bajado: int = 0
    velocidad: float | None = None  # bytes/s
    terminado: bool = False

    def adelantada(self, duracion: int | None, margen_seg: int = 20) -> bool:
        """¿La descarga va a ir siempre por delante de lo que se reproduce, con margen?

        Viendo desde el inicio, la reproducción avanza total/duracion bytes por segundo.
        Si bajamos más rápido que eso, basta con tener el margen; si no, hay que esperar
        a que lo ya bajado compense lo que falta.
        """
        if self.terminado:
            return True
        if not self.total or not duracion:
            return False
        margen = self.total * margen_seg / duracion
        falta_cubrir = max(0.0, self.total - (self.velocidad or 0) * duracion)
        return self.bajado >= min(falta_cubrir + margen, self.total)


@dataclass
class Descarga:
    pistas: dict[str, Pista] = field(default_factory=dict)  # "video" y, si va aparte, "audio"
    miniatura: Path | None = None
    cancelada: bool = False

    @property
    def porcentaje(self) -> int | None:
        total = sum(p.total or 0 for p in self.pistas.values())
        if not total:
            return None
        return round(100 * sum(p.bajado for p in self.pistas.values()) / total)


class Cancelada(Exception):
    pass


def bajar(cfg: Config, vid: str, descarga: Descarga) -> None:
    """Baja video y audio por separado y en paralelo, en orden y sin unirlos al final.

    YouTube los entrega como MP4 fragmentado: un archivo a medio bajar ya se puede reproducir
    hasta donde llegó, así que la tele puede empezar a verlo mientras se sigue bajando.
    Va llenando `descarga` a medida que avanza.
    """
    destino = cfg.carpeta_videos
    destino.mkdir(parents=True, exist_ok=True)
    h = cfg.calidad_max
    opts = _opciones_base(cfg) | {
        # Video H.264 (lo decodifica cualquier tele) + audio M4A; si no existen por separado, uno combinado.
        "format": f"bv*[height<={h}][vcodec^=avc1]+ba[ext=m4a]/bv*[height<={h}]+ba/b[height<={h}]/b",
        "nopart": True,      # escribe directo al archivo final para poder leerlo mientras crece
        "continuedl": False,
        "retries": 5,
        "noplaylist": True,
        "mark_watched": cfg.marcar_visto == "al_bajar",
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(_url(vid), download=False)
        try:
            mini = destino / f"{vid}.jpg"
            mini.write_bytes(ydl.urlopen(f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg").read())
            descarga.miniatura = mini
        except Exception as e:
            log.debug("Sin miniatura para %s: %s", vid, e)

    formatos = info.get("requested_formats") or [info]
    trabajos = []
    for fmt in formatos:
        nombre = "audio" if fmt.get("vcodec") == "none" and len(formatos) > 1 else "video"
        pista = Pista(destino / f"{vid}.{nombre}.{fmt.get('ext') or 'mp4'}", total=fmt.get("filesize"))
        descarga.pistas[nombre] = pista
        datos = {k: v for k, v in info.items() if k != "requested_formats"} | fmt
        trabajos.append((pista, datos))

    abortar = threading.Event()  # si una pista falla, la otra se detiene

    def una(pista: Pista, datos: dict, errores: list) -> None:
        def progreso(d: dict) -> None:
            if descarga.cancelada or abortar.is_set():
                raise Cancelada()
            pista.bajado = d.get("downloaded_bytes") or pista.bajado
            pista.total = d.get("total_bytes") or pista.total
            pista.velocidad = d.get("speed") or pista.velocidad

        try:
            with YoutubeDL(opts | {"progress_hooks": [progreso]}) as ydl:
                if not ydl.dl(str(pista.ruta), datos):
                    raise RuntimeError(f"No se pudo bajar el {pista.ruta.suffix}")
            pista.bajado = pista.ruta.stat().st_size
            pista.total = pista.bajado
            pista.terminado = True
        except Exception as e:
            if not isinstance(e, Cancelada):
                errores.append(e)
                abortar.set()

    errores: list = []
    hilos = [threading.Thread(target=una, args=(p, d, errores), daemon=True) for p, d in trabajos]
    for t in hilos:
        t.start()
    for t in hilos:
        t.join()
    if descarga.cancelada:
        raise Cancelada()
    if errores:
        raise errores[0]


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
