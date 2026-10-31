# Cómo leer el código de YoTV tú solo

## 1. Herramientas
- **Editor:** [VS Code](https://code.visualstudio.com) (gratis). Abre la carpeta `yotv` completa (*File → Open Folder*).
- **Extensiones:** *Python* (de Microsoft) y *Kotlin* (o usa Android Studio para la app de la tele).
- **Atajos que más vas a usar:**
  | Atajo | Para qué |
  |---|---|
  | `Ctrl+clic` sobre un nombre (o `F12`) | saltar a donde está definida esa función |
  | `Shift+F12` | ver todos los lugares donde se usa |
  | `Ctrl+Shift+F` | buscar un texto en todos los archivos |
  | `Ctrl+P` | abrir un archivo escribiendo parte del nombre |
  | pasar el mouse sobre un nombre | ver qué es y su comentario |

## 2. Por dónde empezar (el orden importa)
Lee siguiendo el camino que hace el programa, no los archivos en orden alfabético:

1. `servidor/yotv/__main__.py`: **la puerta de entrada**. Lo que pasa al escribir `python -m yotv correr`: carga la configuración, crea el motor y arranca el servidor.
2. `servidor/yotv/motor.py` → función `ciclo()`: **el corazón**. Cuatro pasos: `limpiar()` → `buscar_nuevos()` → `bajar_cola()` → esperar.
3. Desde ahí, haz `Ctrl+clic` en cada función que llama:
   - `youtube.py`: habla con YouTube (leer el feed, bajar, marcar visto).
   - `curador.py`: arma el texto que se manda a Claude y lee su respuesta.
   - `biblioteca.py`: guarda el estado de cada video en una base de datos.
4. `servidor/yotv/servidor.py`: lo que responde cuando la tele pide algo (`/api/videos`, `/media/...`).
5. App de la tele, `tele-app/app/src/main/java/com/yotv/tele/`:
   - `InicioActivity.kt`: la pantalla de inicio.
   - `ReproductorActivity.kt`: reproduce los videos.
   - `Api.kt`: la que habla con el servidor.

Truco: arriba de cada archivo y de cada función hay un comentario (`"""..."""` en Python, `/** ... */` en Kotlin) que dice para qué sirve. Lee solo esos comentarios primero; después entra al detalle.

## 3. Qué buscar cuando lees una función
1. **Qué recibe** (los parámetros entre paréntesis) y **qué devuelve** (`return`).
2. **Qué cambia**: guarda en la base (`self.bib.actualizar`), escribe archivos, llama a internet.
3. **Los `if`**: ahí están las decisiones ("si ya lo viste, bórralo").
4. Lo que no entiendas, **cópialo y pregúntalo** (a mí o a cualquier buscador): "¿qué hace `threading.Event` en Python?".

## 4. Aprender cambiando cosas (la mejor forma)
- **Las pruebas** (`servidor/tests/test_yotv.py`) son ejemplos de uso: cada `test_...` muestra un caso y lo que debería pasar. Córrelas con `python -m pytest`. Si cambias algo y una prueba se pone roja, ya sabes qué rompiste.
- **Pon `print(...)`** donde quieras ver qué valor tiene algo mientras corre. Por ejemplo, en `curador.py` pon `print(prompt)` antes de llamar a Claude y verás exactamente qué se le manda.
- **Haz cambios pequeños**: sube el margen de 20 a 60 segundos en `Pista.adelantada` (`youtube.py`), corre las pruebas y mira cuál falla y por qué.
- **Usa git como red de seguridad**: `git diff` muestra lo que cambiaste y `git checkout -- archivo` lo deshace.

## 5. Mapa rápido: "quiero cambiar X → archivo"
| Quiero… | Archivo | Busca (`Ctrl+F`) |
|---|---|---|
| que Claude elija distinto | `servidor/yotv/curador.py` | `SISTEMA` |
| cambiar cuándo se borra algo | `servidor/yotv/motor.py` | `def limpiar` |
| cambiar la calidad o el formato | `servidor/yotv/youtube.py` | `"format"` |
| cuánto adelanto se necesita para ver mientras baja | `servidor/yotv/youtube.py` | `margen_seg` |
| colores de la app | `tele-app/app/src/main/res/values/colors.xml` | — |
| qué dice cada tarjeta | `tele-app/.../InicioActivity.kt` | `tarjetaVideo` |
| botones del control en el video | `tele-app/.../ReproductorActivity.kt` | `SeekBack` |
