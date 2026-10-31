import json
import threading
import time
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

from yotv import config, curador
from yotv.biblioteca import Biblioteca
from yotv.motor import Motor
from yotv.servidor import crear_servidor
from yotv.youtube import Cancelada, Descarga, Pista


def candidato(i, canal="Canal A", dur=600, fuente="recomendados"):
    return {"id": f"vid{i:08d}", "titulo": f"Video {i}", "canal": canal, "duracion": dur, "fuente": fuente}


class YouTubeFalso:
    """Reemplaza yotv.youtube: no toca la red."""

    def __init__(self, feed, busquedas=None):
        self.feed = feed
        self.busquedas = busquedas or {}
        self.bajados, self.marcados, self.consultas = [], [], []

    def leer_feeds(self, cfg):
        return list(self.feed)

    def buscar(self, cfg, q, cuantos=6):
        self.consultas.append(q)
        return list(self.busquedas.get(q, []))

    def bajar(self, cfg, vid, descarga):
        cfg.carpeta_videos.mkdir(parents=True, exist_ok=True)
        video = cfg.carpeta_videos / f"{vid}.video.mp4"
        video.write_bytes(b"x" * 1000)
        descarga.pistas["video"] = Pista(video, total=1000, bajado=1000, terminado=True)
        mini = cfg.carpeta_videos / f"{vid}.jpg"
        mini.write_bytes(b"jpg")
        descarga.miniatura = mini
        self.bajados.append(vid)

    def marcar_visto(self, cfg, vid):
        self.marcados.append(vid)


class ClaudeFalso:
    """Imita client.beta.messages.create devolviendo JSON con el esquema del curador."""

    def __init__(self, respuesta):
        self.respuesta = respuesta
        self.pedidos = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.pedidos.append(kw)
        return SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text=json.dumps(self.respuesta))],
            usage=SimpleNamespace(input_tokens=100, output_tokens=20),
        )


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    c = config.Config(carpeta=tmp_path / "datos", videos_listos=3)
    c.carpeta.mkdir()
    return c


def nuevo_motor(cfg, yt, claude=None):
    return Motor(cfg, Biblioteca(cfg.base_datos), yt=yt, cliente_claude=claude)


def test_config_lee_toml_y_rutas_relativas(tmp_path):
    (tmp_path / "cookies.txt").write_text("# Netscape")
    (tmp_path / "config.toml").write_text(
        '[servidor]\ncarpeta="./d"\n[youtube]\ncookies="cookies.txt"\ncalidad_max=720\n'
        '[claude]\nactivado=false\ngustos="cocina"\n'
    )
    c = config.cargar(tmp_path / "config.toml")
    assert c.carpeta == (tmp_path / "d").resolve()
    assert c.cookies == (tmp_path / "cookies.txt").resolve()
    assert c.calidad_max == 720 and c.claude_activado is False and c.gustos == "cocina"


def test_config_rechaza_opciones_desconocidas(tmp_path):
    (tmp_path / "config.toml").write_text("[youtube]\ncalidad=720\n")
    with pytest.raises(ValueError):
        config.cargar(tmp_path / "config.toml")


def test_ciclo_sin_claude_elige_filtra_y_baja(cfg):
    feed = [candidato(1), candidato(2, dur=30), candidato(3, canal="B"), candidato(4, canal="C"),
            candidato(5, canal="D")]
    yt = YouTubeFalso(feed)
    m = nuevo_motor(cfg, yt)
    r = m.ciclo()
    assert r["elegidos"] == 3 and r["bajados"] == 3
    assert "vid00000002" not in yt.bajados  # duró 30 s: es un short
    assert m.bib.contar("listo") == 3
    # Lo no elegido queda como rechazado y no se vuelve a evaluar.
    assert m.bib.obtener("vid00000005")["estado"] == "rechazado"
    assert m.ciclo()["elegidos"] == 0


def test_ciclo_con_claude_usa_numeros_y_guarda_busquedas(cfg):
    feed = [candidato(i, canal=f"C{i}") for i in range(5)]
    claude = ClaudeFalso({"elegidos": [{"n": 4, "motivo": "te gusta el espacio"}, {"n": 99, "motivo": "x"},
                                       {"n": 4, "motivo": "repetido"}, {"n": 1, "motivo": "ok"}],
                          "busquedas": ["agujeros negros", "  "]})
    yt = YouTubeFalso(feed, busquedas={"agujeros negros": [candidato(50, canal="Z")]})
    m = nuevo_motor(cfg, yt, claude)
    m.ciclo()
    assert yt.bajados == ["vid00000004", "vid00000001"]
    assert m.bib.obtener("vid00000004")["motivo"] == "te gusta el espacio"

    pedido = claude.pedidos[0]
    assert pedido["fallbacks"] == "default"
    assert pedido["output_config"]["format"]["type"] == "json_schema"
    assert "4|Video 4|C4|10m" in pedido["messages"][0]["content"]

    # El siguiente ciclo usa la búsqueda que propuso Claude.
    m.ciclo()
    assert yt.consultas == ["agujeros negros"]
    assert "\n0|Video 50|Z|10m" in claude.pedidos[1]["messages"][0]["content"]  # se renumera desde 0


def test_si_claude_falla_usa_reglas(cfg):
    class Roto(ClaudeFalso):
        def _create(self, **kw):
            raise RuntimeError("sin red")
    yt = YouTubeFalso([candidato(1), candidato(2, canal="B")])
    m = nuevo_motor(cfg, yt, Roto({}))
    assert m.ciclo()["bajados"] == 2


def test_progreso_marca_visto_avisa_a_youtube_y_limpia(cfg):
    yt = YouTubeFalso([candidato(1)])
    m = nuevo_motor(cfg, yt)
    m.ciclo()
    vid = "vid00000001"
    m.reportar_progreso(vid, 100, 600)
    assert m.bib.obtener(vid)["estado"] == "listo"
    m.reportar_progreso(vid, 590, 600)
    v = m.bib.obtener(vid)
    assert v["estado"] == "visto"
    time.sleep(0.1)
    assert yt.marcados == [vid]

    archivo = Path(v["archivo"])
    assert archivo.exists()
    cfg.borrar_vistos_tras_horas = 0
    m.limpiar()
    assert not archivo.exists()
    assert m.bib.obtener(vid)["estado"] == "borrado"
    assert m.bib.historial()[0]["titulo"] == "Video 1"


def test_no_me_gusta_borra_al_instante_y_queda_en_historial(cfg):
    yt = YouTubeFalso([candidato(1)])
    m = nuevo_motor(cfg, yt)
    m.ciclo()
    archivo = Path(m.bib.obtener("vid00000001")["archivo"])
    m.opinar("vid00000001", "no_me_gusta")
    assert not archivo.exists()
    h = m.bib.historial()
    assert h[0]["opinion"] == "no_me_gusta"
    assert "[✗] Video 1" in curador.armar_prompt(cfg, h, [candidato(2)], 1)


def test_limite_de_espacio_borra_lo_mas_viejo(cfg):
    cfg.videos_listos = 3
    yt = YouTubeFalso([candidato(1), candidato(2, canal="B"), candidato(3, canal="C")])
    m = nuevo_motor(cfg, yt)
    m.ciclo()
    cfg.max_gb = 2500 / 1024**3  # caben 2 videos de 1000 bytes
    m.limpiar()
    assert m.bib.contar("listo") == 2


def test_servidor_lista_videos_y_sirve_rangos(cfg):
    yt = YouTubeFalso([candidato(1)])
    m = nuevo_motor(cfg, yt)
    m.ciclo()
    srv = crear_servidor(m, host="127.0.0.1", puerto=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        videos = json.load(urllib.request.urlopen(base + "/api/videos"))["videos"]
        assert videos[0]["id"] == "vid00000001" and videos[0]["miniatura"]

        req = urllib.request.Request(base + videos[0]["media"], headers={"Range": "bytes=10-19"})
        with urllib.request.urlopen(req) as r:
            assert r.status == 206
            assert r.headers["Content-Range"] == "bytes 10-19/1000"
            assert r.read() == b"x" * 10

        req = urllib.request.Request(
            base + "/api/videos/vid00000001/progreso", method="POST",
            data=json.dumps({"posicion": 595, "duracion": 600}).encode(),
            headers={"Content-Type": "application/json"},
        )
        assert json.load(urllib.request.urlopen(req))["visto"] is True
        assert "YoTV" in urllib.request.urlopen(base + "/").read().decode()
    finally:
        srv.shutdown()
        srv.server_close()


def test_busquedas_fijas_de_la_config(cfg):
    cfg.busquedas = ["cocina facil"]
    yt = YouTubeFalso([], busquedas={"cocina facil": [candidato(7, canal="Chef")]})
    m = nuevo_motor(cfg, yt)
    assert m.ciclo()["bajados"] == 1
    assert yt.consultas == ["cocina facil"]


def test_descarga_fallida_se_reintenta_tres_veces(cfg):
    class Falla(YouTubeFalso):
        def bajar(self, cfg, vid, descarga):
            self.bajados.append(vid)
            raise RuntimeError("Sign in to confirm you're not a bot")
    yt = Falla([candidato(1)])
    m = nuevo_motor(cfg, yt)
    m.ciclo()
    assert m.bib.obtener("vid00000001")["estado"] == "en_cola"
    m.ciclo()
    m.ciclo()
    v = m.bib.obtener("vid00000001")
    assert v["estado"] == "fallido" and v["intentos"] == 3
    assert yt.bajados == ["vid00000001"] * 3


def test_pista_adelantada():
    # 600 s de video, 60 MB: la reproducción consume 100 KB/s.
    total, dur = 60_000_000, 600
    assert not Pista(Path("x"), total=total, bajado=5_000_000, velocidad=None).adelantada(dur)
    # Baja al doble de lo que se reproduce: basta el margen de 20 s (2 MB).
    assert not Pista(Path("x"), total=total, bajado=1_000_000, velocidad=200_000).adelantada(dur)
    assert Pista(Path("x"), total=total, bajado=2_100_000, velocidad=200_000).adelantada(dur)
    # Baja a la mitad: hay que tener ya la mitad más el margen.
    assert not Pista(Path("x"), total=total, bajado=25_000_000, velocidad=50_000).adelantada(dur)
    assert Pista(Path("x"), total=total, bajado=32_100_000, velocidad=50_000).adelantada(dur)
    # Sin tamaño final o sin duración no se arriesga.
    assert not Pista(Path("x"), total=None, bajado=10**9, velocidad=10**9).adelantada(dur)
    assert Pista(Path("x"), terminado=True).adelantada(None)


class YouTubeLento(YouTubeFalso):
    """Baja video y audio por pasos; el test decide cuándo avanza."""

    def __init__(self, feed):
        super().__init__(feed)
        self.avanzar = threading.Event()
        self.empezo = threading.Event()

    def bajar(self, cfg, vid, descarga):
        cfg.carpeta_videos.mkdir(parents=True, exist_ok=True)
        v = cfg.carpeta_videos / f"{vid}.video.mp4"
        a = cfg.carpeta_videos / f"{vid}.audio.m4a"
        a.write_bytes(b"a" * 100)
        v.write_bytes(b"v" * 400)
        descarga.pistas["video"] = Pista(v, total=1000, bajado=400, velocidad=10**9)
        descarga.pistas["audio"] = Pista(a, total=100, bajado=100, terminado=True)
        self.empezo.set()
        self.avanzar.wait(10)
        if descarga.cancelada:
            raise Cancelada()
        with open(v, "ab") as f:
            f.write(b"w" * 600)
        descarga.pistas["video"].bajado = 1000
        descarga.pistas["video"].terminado = True
        self.bajados.append(vid)


def servir(m):
    srv = crear_servidor(m, host="127.0.0.1", puerto=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def test_se_ve_mientras_se_baja(cfg):
    cfg.videos_listos = 1
    yt = YouTubeLento([candidato(1)])
    m = nuevo_motor(cfg, yt)
    hilo = threading.Thread(target=m.ciclo, daemon=True)
    hilo.start()
    assert yt.empezo.wait(5)
    srv, base = servir(m)
    try:
        videos = json.load(urllib.request.urlopen(base + "/api/videos"))["videos"]
        assert len(videos) == 1
        v = videos[0]
        assert v["bajando"] == 45 and v["audio"].endswith("/audio")

        # La tele pide el video entero: recibe lo bajado y espera el resto sin cortarse.
        recibido = {}

        def leer():
            with urllib.request.urlopen(base + v["media"]) as r:
                recibido["largo"] = r.headers["Content-Length"]
                recibido["datos"] = r.read()

        lector = threading.Thread(target=leer)
        lector.start()
        time.sleep(0.6)
        assert lector.is_alive()  # sigue esperando bytes nuevos
        yt.avanzar.set()
        lector.join(5)
        assert recibido["largo"] == "1000"
        assert recibido["datos"] == b"v" * 400 + b"w" * 600

        assert urllib.request.urlopen(base + v["audio"]).read() == b"a" * 100
        hilo.join(5)
        final = m.bib.obtener("vid00000001")
        assert final["estado"] == "listo" and final["audio"].endswith(".audio.m4a")
        assert final["tamano"] == 1100
        # Ya terminado, el audio se sirve desde el archivo guardado.
        assert urllib.request.urlopen(base + v["audio"]).read() == b"a" * 100
    finally:
        yt.avanzar.set()
        srv.shutdown()
        srv.server_close()


def test_visto_durante_la_descarga_queda_visto(cfg):
    cfg.videos_listos = 1
    yt = YouTubeLento([candidato(1)])
    m = nuevo_motor(cfg, yt)
    hilo = threading.Thread(target=m.ciclo, daemon=True)
    hilo.start()
    assert yt.empezo.wait(5)
    assert m.reportar_progreso("vid00000001", 590, 600)["estado"] == "visto"
    yt.avanzar.set()
    hilo.join(5)
    assert m.bib.obtener("vid00000001")["estado"] == "visto"


def test_no_me_gusta_cancela_la_descarga(cfg):
    cfg.videos_listos = 1
    yt = YouTubeLento([candidato(1)])
    m = nuevo_motor(cfg, yt)
    hilo = threading.Thread(target=m.ciclo, daemon=True)
    hilo.start()
    assert yt.empezo.wait(5)
    m.opinar("vid00000001", "no_me_gusta")
    yt.avanzar.set()
    hilo.join(5)
    assert m.bib.obtener("vid00000001")["estado"] == "borrado"
    assert list(cfg.carpeta_videos.glob("vid00000001.*")) == []
