"""Uso:
    python -m yotv correr  [-c config.toml]   servidor + ciclo automático (lo normal)
    python -m yotv ciclo   [-c config.toml]   un solo ciclo y termina
    python -m yotv estado  [-c config.toml]   muestra qué hay guardado
"""
from __future__ import annotations

import argparse
import logging
import threading
from pathlib import Path

from . import config
from .biblioteca import Biblioteca
from .motor import Motor
from .servidor import crear_servidor


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="yotv", description="Tu canal de YouTube personal para la tele")
    p.add_argument("accion", choices=["correr", "ciclo", "estado"], nargs="?", default="correr")
    p.add_argument("-c", "--config", default="config.toml")
    p.add_argument("-v", "--detalle", action="store_true", help="más mensajes")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.detalle else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S",
    )
    ruta = Path(args.config)
    cfg = config.cargar(ruta if ruta.exists() else None)
    if not ruta.exists():
        logging.warning("No encontré %s; uso valores por defecto (sin cookies, sin feed personal).", ruta)
    cfg.carpeta.mkdir(parents=True, exist_ok=True)
    motor = Motor(cfg, Biblioteca(cfg.base_datos))

    if args.accion == "ciclo":
        print(motor.ciclo())
    elif args.accion == "estado":
        bib = motor.bib
        for estado in ("listo", "en_cola", "visto", "fallido"):
            for v in bib.por_estado(estado):
                print(f"[{estado}] {v['titulo']} — {v['canal']}" + (f"  ({v['error']})" if v["error"] else ""))
        print(f"{bib.bytes_usados() / 1024**3:.2f} GB usados de {cfg.max_gb}")
    else:
        servidor = crear_servidor(motor)
        hilo = threading.Thread(target=motor.correr_siempre, daemon=True)
        hilo.start()
        logging.info("YoTV escuchando en http://0.0.0.0:%d (Claude: %s)", cfg.puerto,
                     "sí" if cfg.usar_claude else "no, reglas simples")
        try:
            servidor.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            motor.parar()
            servidor.server_close()


if __name__ == "__main__":
    main()
