"""Servidor HTTP que usa la app de la tele. Solo biblioteca estándar, para que corra en Termux o en la PS4.

GET  /                         página de estado (ábrela desde el celular)
GET  /api/videos               videos listos para ver
GET  /api/estado               qué está haciendo el motor
GET  /media/<id>               el video (con soporte de Range para adelantar/atrasar)
GET  /media/<id>/audio         el audio, cuando YouTube lo entrega aparte
                               (los dos se pueden pedir mientras todavía se bajan)
GET  /miniatura/<id>           la miniatura
POST /api/videos/<id>/progreso {"posicion": seg, "duracion": seg}
POST /api/videos/<id>/opinion  {"opinion": "me_gusta" | "no_me_gusta"}
POST /api/actualizar           corre un ciclo ya
"""
from __future__ import annotations

import html
import json
import logging
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .motor import Motor

log = logging.getLogger(__name__)
BLOQUE = 256 * 1024
ESPERA_MAX = 60  # segundos esperando bytes nuevos de una descarga antes de cortar

_TIPOS = {".mp4": "video/mp4", ".m4a": "audio/mp4", ".webm": "video/webm", ".mkv": "video/x-matroska"}


def _tipo(ruta: Path) -> str:
    return _TIPOS.get(ruta.suffix, "application/octet-stream")


def _video_publico(v: dict, descarga=None) -> dict:
    con_audio = bool(v.get("audio")) or bool(descarga and "audio" in descarga.pistas)
    return {
        "id": v["id"],
        "titulo": v["titulo"],
        "canal": v["canal"],
        "duracion": v["duracion"],
        "posicion": v["posicion"],
        "motivo": v["motivo"],
        "visto": v["estado"] == "visto",
        "media": f"/media/{v['id']}",
        "audio": f"/media/{v['id']}/audio" if con_audio else None,
        "bajando": descarga.porcentaje if descarga else None,
        "miniatura": f"/miniatura/{v['id']}" if v["miniatura"] or (descarga and descarga.miniatura) else None,
    }


def crear_servidor(motor: Motor, host: str = "0.0.0.0", puerto: int | None = None) -> ThreadingHTTPServer:
    bib = motor.bib

    class Manejador(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "YoTV"

        def log_message(self, fmt, *args):
            log.debug("%s - %s", self.address_string(), fmt % args)

        # ---------- utilidades ----------
        def _json(self, datos, codigo: int = 200) -> None:
            cuerpo = json.dumps(datos, ensure_ascii=False).encode()
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def _leer_json(self) -> dict:
            largo = int(self.headers.get("Content-Length") or 0)
            if not largo:
                return {}
            try:
                return json.loads(self.rfile.read(largo))
            except json.JSONDecodeError:
                return {}

        def _archivo(self, ruta: Path, tipo: str, pista=None) -> None:
            """Envía un archivo. Si `pista` sigue bajándose, anuncia el tamaño final y espera
            los bytes que todavía no llegan, así la tele lo ve como una conexión lenta."""
            if not ruta.is_file():
                return self._json({"error": "no existe"}, 404)
            creciendo = pista is not None and not pista.terminado and pista.total
            total = pista.total if creciendo else ruta.stat().st_size
            inicio, fin, codigo = 0, total - 1, 200
            rango = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
            if rango and (rango[1] or rango[2]):
                if rango[1]:
                    inicio = int(rango[1])
                    fin = min(int(rango[2]), total - 1) if rango[2] else total - 1
                else:  # bytes=-N: los últimos N bytes
                    inicio = max(total - int(rango[2]), 0)
                if inicio > fin or inicio >= total:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{total}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                codigo = 206
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(fin - inicio + 1))
            if codigo == 206:
                self.send_header("Content-Range", f"bytes {inicio}-{fin}/{total}")
            self.end_headers()
            if self.command == "HEAD":
                return
            with open(ruta, "rb") as f:
                f.seek(inicio)
                restante = fin - inicio + 1
                vacio_desde = None
                try:
                    while restante > 0:
                        trozo = f.read(min(BLOQUE, restante))
                        if trozo:
                            self.wfile.write(trozo)
                            restante -= len(trozo)
                            vacio_desde = None
                            continue
                        # Llegamos a lo bajado: esperar más, salvo que ya no vaya a llegar nada.
                        if not creciendo or (pista.terminado and vacio_desde is not None):
                            break
                        vacio_desde = vacio_desde or time.monotonic()
                        if time.monotonic() - vacio_desde > ESPERA_MAX:
                            break
                        time.sleep(0.25)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # la tele cerró la conexión al adelantar: normal

        def _estado(self) -> dict:
            actual = next(iter(motor.descargas.values()), None)
            return {
                **motor.estado,
                "progreso": actual.porcentaje if actual else None,
                "listos": bib.contar("listo"),
                "en_cola": bib.contar("en_cola", "bajando"),
                "vistos": bib.contar("visto"),
                "gb_usados": round(bib.bytes_usados() / 1024**3, 2),
                "gb_max": motor.cfg.max_gb,
                "con_claude": motor.cfg.usar_claude,
            }

        # ---------- rutas ----------
        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            ruta = self.path.split("?")[0]
            if ruta == "/api/videos":
                videos = [v for v in bib.por_estado("listo", "visto", "bajando", orden="listo_en")
                          if motor.se_puede_ver(v)]
                # Lo que dejaste a medias, lo listo, lo que se está bajando y al final lo ya visto.
                videos.sort(key=lambda v: (v["estado"] == "visto", not v["posicion"],
                                           v["estado"] == "bajando", v["listo_en"] or 0))
                return self._json({"videos": [_video_publico(v, motor.descargas.get(v["id"])) for v in videos]})
            if ruta == "/api/estado":
                return self._json(self._estado())
            if m := re.fullmatch(r"/media/([\w-]{6,20})(/audio)?", ruta):
                nombre = "audio" if m[2] else "video"
                d = motor.descargas.get(m[1])
                if d and nombre in d.pistas:
                    pista = d.pistas[nombre]
                    return self._archivo(pista.ruta, _tipo(pista.ruta), pista)
                v = bib.obtener(m[1])
                archivo = v and v["audio" if m[2] else "archivo"]
                if archivo:
                    return self._archivo(Path(archivo), _tipo(Path(archivo)))
                return self._json({"error": "no existe"}, 404)
            if m := re.fullmatch(r"/miniatura/([\w-]{6,20})", ruta):
                d = motor.descargas.get(m[1])
                v = bib.obtener(m[1])
                mini = (d and d.miniatura) or (v and v["miniatura"])
                if mini:
                    return self._archivo(Path(mini), "image/jpeg")
                return self._json({"error": "no existe"}, 404)
            if ruta == "/":
                return self._pagina()
            self._json({"error": "ruta desconocida"}, 404)

        def do_POST(self):
            ruta = self.path.split("?")[0]
            datos = self._leer_json()
            if m := re.fullmatch(r"/api/videos/([\w-]{6,20})/progreso", ruta):
                try:
                    pos = int(datos["posicion"])
                    dur = int(datos["duracion"]) if datos.get("duracion") else None
                except (KeyError, TypeError, ValueError):
                    return self._json({"error": "falta posicion"}, 400)
                v = motor.reportar_progreso(m[1], pos, dur)
                return self._json(_video_publico(v)) if v else self._json({"error": "no existe"}, 404)
            if m := re.fullmatch(r"/api/videos/([\w-]{6,20})/opinion", ruta):
                v = motor.opinar(m[1], datos.get("opinion", ""))
                return self._json({"ok": True}) if v else self._json({"error": "opinión inválida"}, 400)
            if ruta == "/api/actualizar":
                motor.despertar()
                if "form-urlencoded" in self.headers.get("Content-Type", ""):  # botón de la página
                    self.send_response(303)
                    self.send_header("Location", "/")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                return self._json({"ok": True})
            self._json({"error": "ruta desconocida"}, 404)

        def _pagina(self) -> None:
            e = self._estado()
            filas = "".join(
                f"<li>{html.escape(v['titulo'])} <small>— {html.escape(v['canal'] or '')} · "
                f"{html.escape(v['motivo'] or '')}</small></li>"
                for v in bib.por_estado("listo", orden="listo_en")
            )
            cola = "".join(f"<li>{html.escape(v['titulo'])}</li>" for v in bib.por_estado("en_cola", "bajando"))
            proximo = time.strftime("%H:%M", time.localtime(e["proximo_ciclo"])) if e["proximo_ciclo"] else "—"
            bajando = f"{html.escape(e['bajando'])} ({e['progreso'] or 0}%)" if e["bajando"] else "nada"
            cuerpo = f"""<!doctype html><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>YoTV</title>
<style>body{{font-family:system-ui;background:#111;color:#eee;max-width:720px;margin:auto;padding:16px}}
small{{color:#999}} button{{font-size:1rem;padding:8px 16px}} .err{{color:#f77}}</style>
<h1>YoTV</h1>
<p>Fase: <b>{e['fase']}</b> · Bajando: {bajando} · Próximo ciclo: {proximo}</p>
<p>{e['listos']} listos · {e['en_cola']} en cola · {e['gb_usados']} / {e['gb_max']} GB ·
Claude: {'sí' if e['con_claude'] else 'no (reglas simples)'}</p>
{f"<p class=err>Último error: {html.escape(e['ultimo_error'])}</p>" if e['ultimo_error'] else ''}
<form method=post action=/api/actualizar><button>Buscar videos ahora</button></form>
<h2>Listos</h2><ol>{filas or '<i>nada todavía</i>'}</ol>
<h2>En cola</h2><ol>{cola or '<i>vacía</i>'}</ol>"""
            datos = cuerpo.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(datos)))
            self.end_headers()
            self.wfile.write(datos)

    servidor = ThreadingHTTPServer((host, puerto if puerto is not None else motor.cfg.puerto), Manejador)
    servidor.daemon_threads = True
    return servidor
