# YoTV: tu canal personal de YouTube en la tele

YoTV convierte tu tele (Google TV / Android TV, como tu TCL) en un canal hecho para ti:

- **Baja solo** videos de tu feed de YouTube (recomendados y suscripciones) y de búsquedas que tú o Claude elijan.
- **Claude elige** qué vale la pena según lo que ves, lo que saltas y lo que marcas con "me gusta" / "no me gusta".
- **Se ven sin anuncios ni buffering**, porque ya están guardados.
- **Se borran solos** cuando los terminas (o si pasan días sin que los veas) y se bajan otros en su lugar.
- **Le enseña a YouTube**: cuando terminas un video, YoTV lo marca como visto en tu cuenta, así tus recomendaciones mejoran con lo que de verdad ves.
- **No esperas a que termine de bajar**: video y audio se bajan en paralelo y en orden. Un video aparece en la tele apenas la descarga va lo bastante rápida para ir siempre por delante de lo que estás viendo (con 20 s de margen). En la tarjeta dice "Bajando 35 % · ya puedes verlo".
- La app puede ser **la pantalla de inicio** de la tele: tus videos, tus apps y los ajustes, sin publicidad.

```
┌────────────── servidor (Python) ───────────────┐         ┌──── app YoTV en la tele ────┐
│ cada hora:                                     │  Wi-Fi  │ fila "Para ti" con miniaturas │
│  1. limpia lo visto / viejo / lo que sobra     │ ──────▶ │ reproductor (sigue donde      │
│  2. lee tu feed con yt-dlp (solo títulos)      │         │   lo dejaste, pasa al próximo)│
│  3. Claude elige de una lista numerada         │ ◀────── │ avisa hasta dónde viste,      │
│  4. baja en MP4 1080p                          │         │   me gusta / no me gusta      │
└────────────────────────────────────────────────┘         └───────────────────────────────┘
   corre en: la misma tele (Termux)  ·  la PS4 con Linux  ·  cualquier compu o Raspberry Pi
```

> Bajar videos de YouTube va contra sus términos de servicio. Úsalo solo para ti y no compartas los archivos.

---

## Paso 1: instalar la app en la tele

1. En la tele: **Configuración → Sistema → Información** y presiona **Compilación** 7 veces. Se activan las *Opciones de desarrollador*.
2. En **Opciones de desarrollador** activa **Depuración USB** y **Depuración por red** (o "ADB por red").
3. En tu compu instala [platform-tools de Android](https://developer.android.com/tools/releases/platform-tools) y, con la IP de la tele (Configuración → Red), corre:

```bash
adb connect 192.168.1.50:5555        # la IP de tu tele; acepta el aviso que sale en pantalla
adb install -r YoTV.apk              # el archivo YoTV.apk de esta carpeta
```

YoTV aparece en tus apps. Para que sea **la pantalla de inicio** (lo que sale al presionar Home):

```bash
adb shell cmd package set-home-activity com.yotv.tele/.InicioActivity
```

Para volver al inicio original, primero mira cómo se llama en tu modelo y luego ponlo de nuevo:

```bash
adb shell pm query-activities --brief -a android.intent.action.MAIN -c android.intent.category.HOME
# en Google TV suele ser: com.google.android.apps.tv.launcherx/.home.HomeActivity
adb shell cmd package set-home-activity com.google.android.apps.tv.launcherx/.home.HomeActivity
```

> Si tu modelo no respeta el cambio de Home, abre YoTV desde las apps; todo lo demás funciona igual.
> Para quitar también los anuncios del sistema puedes combinarlo con [CleanTV](https://github.com/JohnWayneeee/cleantv).

---

## Paso 2: elegir dónde corre el servidor

El servidor es el que baja y borra los videos. Elige **una** opción:

### Opción A: dentro de la misma tele (Termux)

Lo más simple, pero el espacio de la tele es chico (pon `max_gb = 5` en la configuración) y solo baja mientras la tele está prendida o en reposo.

```bash
# desde tu compu, con la tele conectada por adb:
adb install termux.apk          # bájalo de https://f-droid.org/packages/com.termux/
adb install termux-boot.apk     # https://f-droid.org/packages/com.termux.boot/ (arranque automático)
adb push servidor /sdcard/yotv
```

Abre **Termux** en la tele. Para escribir es más cómodo usar el teclado de la app *Google TV* del celular. Luego:

```bash
termux-setup-storage            # acepta el permiso
cp -r ~/storage/shared/yotv ~/yotv && cd ~/yotv
bash instalar-termux.sh
nano config.toml                # ajusta gustos, max_gb, etc. (Ctrl+O guarda, Ctrl+X sale)
termux-wake-lock; python -m yotv correr
```

Abre **Termux:Boot** una vez para que YoTV arranque solo cada vez que prendas la tele. En la app YoTV deja el servidor en `http://127.0.0.1:8765`.

### Opción B: la PS4 con Linux, una compu vieja o una Raspberry Pi

Esta opción es mejor si quieres más espacio (el disco de la PS4) y descargas 24/7 sin cargar la tele.

- **PS4:** para correr Linux necesitas una PS4 con un firmware que se pueda desbloquear (jailbreak) y una distro para PS4 (normalmente en un disco USB). Eso depende de tu versión de firmware y se hace aparte. Una vez que Linux arranca, sigue igual que en cualquier compu.
- **Cualquier Linux:**

```bash
cd servidor
bash instalar-linux.sh          # instala todo y deja un servicio que arranca solo
nano config.toml
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
sudo systemctl restart yotv
```

En la app YoTV de la tele: **Sistema → Ajustes de YoTV**, escribe `http://IP-DE-LA-PS4:8765` y presiona **Probar y guardar**.

---

## Paso 3: conectar tu cuenta de YouTube (cookies)

Sin esto YoTV solo puede usar `canales` y `busquedas` de la configuración. Con tus cookies lee **tu** feed de recomendados y suscripciones.

1. En la compu, instala la extensión **"Get cookies.txt LOCALLY"** (Chrome o Firefox).
2. Abre una **ventana de incógnito**, entra a youtube.com con tu cuenta y exporta las cookies de youtube.com.
3. **Cierra esa ventana de incógnito** (si la sigues usando, YouTube cambia las cookies y dejan de servir).
4. Guarda el archivo como `cookies.txt` en la carpeta `servidor` (en Termux: `adb push cookies.txt /sdcard/yotv/` y luego `cp ~/storage/shared/yotv/cookies.txt ~/yotv/`).

> YouTube puede marcar cuentas con mucha actividad automática. Si te preocupa, usa una cuenta secundaria de Google entrenada con tus gustos.

---

## Paso 4: Claude (opcional, recomendado)

Saca una API key en [console.anthropic.com](https://console.anthropic.com) y ponla en `.env` (`ANTHROPIC_API_KEY=...`) o en `config.toml` (`api_key = "..."`).

**Cómo ahorra tokens:** Claude no navega ni abre videos. yt-dlp lee tu feed gratis (solo títulos, canal y duración) y Claude recibe una línea por video (`7|Título|Canal|12m`) más tu historial reciente. Responde solo números, motivos cortos y búsquedas nuevas. Es **una llamada por ciclo**, y solo cuando hace falta bajar más.

**Costo aproximado** (unas 10 llamadas al día, ~2 000 tokens cada una):

| Modelo | Por llamada | Al mes |
|---|---|---|
| `claude-opus-5-5` (por defecto) | ~US$0,015 | ~US$4–5 |
| `claude-haiku-5-5` | ~US$0,0005 | ~US$0,15 |

Para elegir videos, Haiku alcanza de sobra: cambia `modelo = "claude-haiku-5-5"` en `config.toml` si quieres que salga casi gratis. Sin API key, YoTV usa reglas simples: prioriza los canales que ya terminaste y evita los que marcaste con "no me gusta".

---

## Uso con el control remoto

| Dónde | Botón | Qué hace |
|---|---|---|
| Inicio | OK | reproduce desde ese video (sigue solo con los demás) |
| Inicio | **mantener OK** | ♥ Me gusta (más como este) / ✗ No me gusta (se borra ya) |
| Video | ← / → | atrás 10 s / adelante 30 s |
| Video | Atrás | sale; la próxima vez sigue donde lo dejaste |
| Inicio | fila Sistema | buscar videos ahora, ajustes de YoTV, ajustes de la tele |

Desde el celular puedes ver qué está bajando en `http://IP-DEL-SERVIDOR:8765`.

## Cómo aprende

1. Lo que **terminas** (90 % o más) se marca como visto en tu cuenta de YouTube y te llegan recomendaciones parecidas.
2. Lo que **abres y abandonas** queda como "saltado" en el historial que ve Claude.
3. **Me gusta / no me gusta** pesa directo en la próxima elección.
4. Claude propone **búsquedas nuevas** cada ciclo para descubrir cosas fuera de tu feed.
5. En `gustos` de `config.toml` puedes escribir con tus palabras qué te gusta y qué no.

## Configuración

Todo está explicado en [`servidor/config.ejemplo.toml`](servidor/config.ejemplo.toml): espacio máximo, cuántos videos tener listos, cuándo borrar, calidad (720 baja el doble de rápido), duración mínima/máxima, fuentes y modelo de Claude.

## Problemas comunes

- **"Sign in to confirm you're not a bot"**: faltan cookies o caducaron. Vuelve a exportarlas (paso 3).
- **La app dice "Sin conexión con el servidor"**: revisa que el servidor esté corriendo y que la IP en *Ajustes de YoTV* sea la correcta.
- **No baja nada**: mira `python -m yotv estado` o la página web del servidor. Los errores aparecen ahí.
- **Se llena el disco**: baja `max_gb` o `videos_listos`.
- **Se queda cargando al adelantar un video que se está bajando**: es normal si saltas más allá de lo ya bajado; espera unos segundos o vuelve atrás.

## Para desarrolladores

- Servidor: `servidor/`, Python 3.11+ con solo `yt-dlp` y `anthropic`. Pruebas: `cd servidor && python -m pytest`. Para entender el código por tu cuenta, lee [COMO-LEER-EL-CODIGO.md](COMO-LEER-EL-CODIGO.md).
- App: `tele-app/`, Kotlin + Media3, sin otras dependencias. Compilar: `cd tele-app && ./gradlew assembleRelease`. La llave de firma (`app/yotv.keystore`) es fija a propósito para que las versiones nuevas se instalen encima; es solo para uso personal.
