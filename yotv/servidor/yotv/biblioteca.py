"""Base de datos SQLite con el estado de cada video.

Estados:
  rechazado   Claude (o el filtro) lo vio y no lo eligió. Se guarda para no volver a evaluarlo.
  en_cola     elegido, esperando descarga
  bajando     descargándose ahora (ya se puede ver si la descarga va adelantada)
  listo       descargado y sin ver
  visto       lo terminaste; se borra tras unas horas
  borrado     archivo eliminado
  fallido     la descarga falló 3 veces
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS videos (
    id          TEXT PRIMARY KEY,
    titulo      TEXT NOT NULL,
    canal       TEXT,
    duracion    INTEGER,
    fuente      TEXT,
    motivo      TEXT,
    estado      TEXT NOT NULL,
    archivo     TEXT,
    audio       TEXT,
    miniatura   TEXT,
    tamano      INTEGER DEFAULT 0,
    agregado    REAL,
    listo_en    REAL,
    abierto_en  REAL,
    visto_en    REAL,
    posicion    INTEGER DEFAULT 0,
    opinion     TEXT,
    error       TEXT,
    intentos    INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS videos_estado ON videos(estado);
CREATE TABLE IF NOT EXISTS meta (clave TEXT PRIMARY KEY, valor TEXT);
"""


class Biblioteca:
    def __init__(self, ruta: Path | str):
        self._con = sqlite3.connect(str(ruta), check_same_thread=False)
        self._con.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._con.executescript(ESQUEMA)
            # Si el programa se cortó a mitad de una descarga, vuelve a la cola.
            self._con.execute("UPDATE videos SET estado='en_cola' WHERE estado='bajando'")
            self._con.commit()

    def _ejecutar(self, sql: str, params=()) -> list[sqlite3.Row]:
        with self._lock:
            filas = self._con.execute(sql, params).fetchall()
            self._con.commit()
            return filas

    # --- consulta ---
    def obtener(self, vid: str) -> dict | None:
        filas = self._ejecutar("SELECT * FROM videos WHERE id=?", (vid,))
        return dict(filas[0]) if filas else None

    def conocidos(self) -> set[str]:
        return {f["id"] for f in self._ejecutar("SELECT id FROM videos")}

    def por_estado(self, *estados: str, orden: str = "agregado") -> list[dict]:
        marcas = ",".join("?" * len(estados))
        sql = f"SELECT * FROM videos WHERE estado IN ({marcas}) ORDER BY {orden}"
        return [dict(f) for f in self._ejecutar(sql, estados)]

    def contar(self, *estados: str) -> int:
        marcas = ",".join("?" * len(estados))
        return self._ejecutar(f"SELECT COUNT(*) c FROM videos WHERE estado IN ({marcas})", estados)[0]["c"]

    def bytes_usados(self) -> int:
        fila = self._ejecutar(
            "SELECT COALESCE(SUM(tamano),0) s FROM videos WHERE estado IN ('listo','visto')"
        )
        return fila[0]["s"]

    def historial(self, limite: int = 20) -> list[dict]:
        """Lo último que viste o calificaste: es lo que Claude usa para conocerte."""
        sql = """SELECT titulo, canal, opinion, estado, posicion, duracion FROM videos
                 WHERE abierto_en IS NOT NULL OR opinion IS NOT NULL
                 ORDER BY COALESCE(visto_en, abierto_en, listo_en) DESC LIMIT ?"""
        return [dict(f) for f in self._ejecutar(sql, (limite,))]

    # --- cambios ---
    def agregar(self, video: dict, estado: str, motivo: str | None = None) -> None:
        self._ejecutar(
            """INSERT OR IGNORE INTO videos (id, titulo, canal, duracion, fuente, motivo, estado, agregado)
               VALUES (?,?,?,?,?,?,?,?)""",
            (video["id"], video["titulo"], video.get("canal"), video.get("duracion"),
             video.get("fuente"), motivo, estado, time.time()),
        )

    def actualizar(self, vid: str, **campos) -> None:
        if not campos:
            return
        asignaciones = ", ".join(f"{k}=?" for k in campos)
        self._ejecutar(f"UPDATE videos SET {asignaciones} WHERE id=?", (*campos.values(), vid))

    # --- meta (pequeño almacén clave/valor) ---
    def meta(self, clave: str, defecto: str | None = None) -> str | None:
        filas = self._ejecutar("SELECT valor FROM meta WHERE clave=?", (clave,))
        return filas[0]["valor"] if filas else defecto

    def guardar_meta(self, clave: str, valor: str) -> None:
        self._ejecutar("INSERT OR REPLACE INTO meta (clave, valor) VALUES (?,?)", (clave, valor))
