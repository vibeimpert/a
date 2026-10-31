"""El ciclo que corre solo: limpiar -> buscar candidatos -> elegir -> bajar."""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

from . import curador, youtube
from .biblioteca import Biblioteca
from .config import Config

log = logging.getLogger(__name__)


def _borrar_archivos(video: dict) -> None:
    for campo in ("archivo", "audio", "miniatura"):
        if video.get(campo):
            Path(video[campo]).unlink(missing_ok=True)


class Motor:
    def __init__(self, cfg: Config, bib: Biblioteca, yt=youtube, cliente_claude=None):
        self.cfg = cfg
        self.bib = bib
        self.yt = yt
        self.cliente_claude = cliente_claude
        self._despertar = threading.Event()
        self._parar = threading.Event()
        self.estado = {"fase": "esperando", "ultimo_ciclo": None, "proximo_ciclo": None,
                       "ultimo_error": None, "bajando": None}
        self.descargas: dict[str, youtube.Descarga] = {}  # lo que se está bajando ahora

    # ---------- limpieza ----------
    def limpiar(self) -> int:
        ahora = time.time()
        borrados = 0

        def borrar(v: dict, estado: str = "borrado") -> None:
            nonlocal borrados
            _borrar_archivos(v)
            self.bib.actualizar(v["id"], estado=estado, archivo=None, audio=None, miniatura=None, tamano=0)
            borrados += 1

        limite_vistos = ahora - self.cfg.borrar_vistos_tras_horas * 3600
        for v in self.bib.por_estado("visto"):
            if (v["visto_en"] or 0) <= limite_vistos:
                borrar(v)

        limite_viejos = ahora - self.cfg.borrar_sin_ver_tras_dias * 86400
        for v in self.bib.por_estado("listo"):
            if (v["listo_en"] or 0) <= limite_viejos:
                borrar(v)

        # Si aún se pasa del espacio, primero lo visto y luego lo más viejo sin ver.
        if self.bib.bytes_usados() > self.cfg.max_bytes:
            for v in self.bib.por_estado("visto", orden="visto_en") + self.bib.por_estado("listo", orden="listo_en"):
                if self.bib.bytes_usados() <= self.cfg.max_bytes:
                    break
                borrar(v)
        return borrados

    # ---------- elegir ----------
    def buscar_nuevos(self, cuantos: int) -> int:
        conocidos = self.bib.conocidos()
        candidatos, ids = [], set()
        busquedas = self.cfg.busquedas + json.loads(self.bib.meta("busquedas_pendientes", "[]"))
        fuentes = self.yt.leer_feeds(self.cfg) + [
            c for q in busquedas for c in self.yt.buscar(self.cfg, q)
        ]
        for c in fuentes:
            if c["id"] in conocidos or c["id"] in ids:
                continue
            d = c["duracion"]
            if d is not None and not (self.cfg.duracion_min_seg <= d <= self.cfg.duracion_max_seg):
                continue
            ids.add(c["id"])
            candidatos.append(c)

        log.info("%d candidatos nuevos", len(candidatos))
        decision = curador.elegir(
            self.cfg, self.bib.historial(), candidatos, cuantos, cliente=self.cliente_claude
        )
        elegidos = {c["id"] for c, _ in decision.elegidos}
        for c, motivo in decision.elegidos:
            self.bib.agregar(c, "en_cola", motivo)
        for c in candidatos:
            if c["id"] not in elegidos:
                self.bib.agregar(c, "rechazado")
        self.bib.guardar_meta("busquedas_pendientes", json.dumps(decision.busquedas, ensure_ascii=False))
        return len(decision.elegidos)

    # ---------- bajar ----------
    def bajar_cola(self) -> int:
        bajados = 0
        for v in self.bib.por_estado("en_cola"):
            if self._parar.is_set() or self.bib.bytes_usados() >= self.cfg.max_bytes:
                break
            self.bib.actualizar(v["id"], estado="bajando")
            self.estado["bajando"] = v["titulo"]
            descarga = youtube.Descarga()
            self.descargas[v["id"]] = descarga
            try:
                self.yt.bajar(self.cfg, v["id"], descarga)
                if descarga.cancelada:  # "no me gusta" justo cuando terminaba
                    raise youtube.Cancelada()
                video, audio = descarga.pistas["video"], descarga.pistas.get("audio")
                # Si lo terminaste de ver mientras se bajaba, queda como visto.
                ya_visto = self.bib.obtener(v["id"])["estado"] == "visto"
                self.bib.actualizar(
                    v["id"], estado="visto" if ya_visto else "listo", archivo=str(video.ruta),
                    audio=str(audio.ruta) if audio else None,
                    miniatura=str(descarga.miniatura) if descarga.miniatura else None,
                    tamano=sum(p.ruta.stat().st_size for p in descarga.pistas.values()),
                    listo_en=time.time(), error=None,
                )
                bajados += 1
                log.info("Listo: %s", v["titulo"])
            except youtube.Cancelada:
                log.info("Cancelado: %s", v["titulo"])
                self._borrar_parciales(descarga)
            except Exception as e:
                self._borrar_parciales(descarga)
                intentos = (v["intentos"] or 0) + 1
                log.warning("Falló la descarga de %s (intento %d): %s", v["titulo"], intentos, e)
                # Los errores pasajeros (red, "confirma que no eres un bot") se reintentan el próximo ciclo.
                self.bib.actualizar(v["id"], estado="fallido" if intentos >= 3 else "en_cola",
                                    intentos=intentos, error=str(e)[:500])
            finally:
                self.descargas.pop(v["id"], None)
                self.estado["bajando"] = None
        return bajados

    @staticmethod
    def _borrar_parciales(descarga: youtube.Descarga) -> None:
        for p in descarga.pistas.values():
            p.ruta.unlink(missing_ok=True)
        if descarga.miniatura:
            descarga.miniatura.unlink(missing_ok=True)

    def se_puede_ver(self, v: dict) -> bool:
        """Listo, o bajándose lo bastante rápido como para verlo sin alcanzar a la descarga."""
        if v["estado"] in ("listo", "visto"):
            return True
        d = self.descargas.get(v["id"])
        return bool(
            v["estado"] == "bajando" and d and "video" in d.pistas
            and all(p.adelantada(v["duracion"]) for p in d.pistas.values())
        )

    # ---------- ciclo ----------
    def ciclo(self) -> dict:
        resumen = {"borrados": 0, "elegidos": 0, "bajados": 0}
        self.estado["fase"] = "limpiando"
        resumen["borrados"] = self.limpiar()

        faltan = self.cfg.videos_listos - self.bib.contar("listo", "en_cola", "bajando")
        if faltan > 0 and self.bib.bytes_usados() < self.cfg.max_bytes:
            self.estado["fase"] = "eligiendo"
            resumen["elegidos"] = self.buscar_nuevos(faltan)

        self.estado["fase"] = "bajando"
        resumen["bajados"] = self.bajar_cola()
        self.estado["fase"] = "esperando"
        self.estado["ultimo_ciclo"] = time.time()
        log.info("Ciclo terminado: %s", resumen)
        return resumen

    def despertar(self) -> None:
        self._despertar.set()

    def parar(self) -> None:
        self._parar.set()
        self._despertar.set()

    def correr_siempre(self) -> None:
        while not self._parar.is_set():
            try:
                self.ciclo()
                self.estado["ultimo_error"] = None
            except Exception as e:
                log.exception("Error en el ciclo")
                self.estado["ultimo_error"] = str(e)
                self.estado["fase"] = "esperando"
            espera = self.cfg.cada_minutos * 60
            self.estado["proximo_ciclo"] = time.time() + espera
            self._despertar.wait(espera)
            self._despertar.clear()

    # ---------- lo que reporta la tele ----------
    def reportar_progreso(self, vid: str, posicion: int, duracion: int | None) -> dict | None:
        v = self.bib.obtener(vid)
        if not v or v["estado"] not in ("listo", "visto", "bajando"):
            return None
        cambios: dict = {"posicion": int(posicion), "abierto_en": time.time()}
        duracion = duracion or v["duracion"]
        if duracion and not v["duracion"]:
            cambios["duracion"] = int(duracion)
        termino = bool(duracion) and posicion >= 0.9 * duracion
        if termino and v["estado"] in ("listo", "bajando"):
            cambios |= {"estado": "visto", "visto_en": time.time()}
            if self.cfg.marcar_visto == "al_ver":
                threading.Thread(target=self.yt.marcar_visto, args=(self.cfg, vid), daemon=True).start()
            self.despertar()  # quedó un hueco: busca reemplazo
        self.bib.actualizar(vid, **cambios)
        return self.bib.obtener(vid)

    def opinar(self, vid: str, opinion: str) -> dict | None:
        v = self.bib.obtener(vid)
        if not v or opinion not in ("me_gusta", "no_me_gusta"):
            return None
        if opinion == "no_me_gusta" and v["estado"] in ("listo", "visto", "bajando", "en_cola"):
            if vid in self.descargas:
                self.descargas[vid].cancelada = True  # la descarga se corta y borra lo parcial
            _borrar_archivos(v)
            self.bib.actualizar(vid, opinion=opinion, estado="borrado", archivo=None, audio=None,
                                miniatura=None, tamano=0, abierto_en=time.time())
            self.despertar()
        else:
            self.bib.actualizar(vid, opinion=opinion, abierto_en=v["abierto_en"] or time.time())
            if opinion == "me_gusta" and self.cfg.marcar_visto != "nunca":
                threading.Thread(target=self.yt.marcar_visto, args=(self.cfg, vid), daemon=True).start()
        return self.bib.obtener(vid)
