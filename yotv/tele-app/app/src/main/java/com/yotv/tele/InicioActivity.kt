package com.yotv.tele

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.graphics.Color
import android.graphics.drawable.ColorDrawable
import android.graphics.drawable.Drawable
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.text.TextUtils
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.HorizontalScrollView
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast

/** Pantalla de inicio: tus videos, tus apps y accesos al sistema. Puede reemplazar el inicio de la tele. */
class InicioActivity : Activity() {
    private lateinit var filas: LinearLayout
    private lateinit var estado: TextView
    private val reloj = Handler(Looper.getMainLooper())
    private val refrescar = object : Runnable {
        override fun run() {
            cargarVideos()
            reloj.postDelayed(this, 60_000)
        }
    }
    private var filaVideos: LinearLayout? = null
    private var videos: List<Video> = emptyList()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_inicio)
        filas = findViewById(R.id.filas)
        estado = findViewById(R.id.estado)
        armarFilas()
    }

    override fun onResume() {
        super.onResume()
        reloj.post(refrescar)
    }

    override fun onPause() {
        super.onPause()
        reloj.removeCallbacks(refrescar)
    }

    @Deprecated("Usado por Android TV para el botón Atrás")
    override fun onBackPressed() {
        // Si somos el inicio de la tele, Atrás no debe dejar la pantalla en negro.
        if (intent?.hasCategory(Intent.CATEGORY_HOME) != true) super.onBackPressed()
    }

    private fun dp(v: Int) = TypedValue.applyDimension(
        TypedValue.COMPLEX_UNIT_DIP, v.toFloat(), resources.displayMetrics).toInt()

    private fun armarFilas() {
        filas.removeAllViews()
        filaVideos = agregarFila("Para ti")
        val apps = agregarFila("Apps")
        cargarApps(apps)
        val sistema = agregarFila("Sistema")
        sistema.addView(tarjetaSimple("Buscar videos ahora", null) {
            Fondo.correr({ Api.de(this).actualizar() },
                { aviso("Buscando videos nuevos…") }, { aviso("No hay conexión con el servidor") })
        })
        sistema.addView(tarjetaSimple("Ajustes de YoTV", null) {
            startActivity(Intent(this, AjustesActivity::class.java))
        })
        sistema.addView(tarjetaSimple("Ajustes de la tele", null) {
            startActivity(Intent(Settings.ACTION_SETTINGS))
        })
    }

    private fun agregarFila(titulo: String): LinearLayout {
        filas.addView(TextView(this).apply {
            text = titulo
            setTextColor(getColor(R.color.texto))
            textSize = 20f
            setPadding(0, dp(18), 0, dp(8))
        })
        val contenido = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(dp(4), dp(8), dp(4), dp(8))
        }
        filas.addView(HorizontalScrollView(this).apply {
            isHorizontalScrollBarEnabled = false
            clipToPadding = false
            clipChildren = false
            addView(contenido)
        })
        return contenido
    }

    private fun alEnfocar(v: View) {
        v.setOnFocusChangeListener { vista, enfocado ->
            val escala = if (enfocado) 1.08f else 1f
            vista.animate().scaleX(escala).scaleY(escala).setDuration(120).start()
            vista.elevation = if (enfocado) dp(8).toFloat() else 0f
        }
    }

    private fun texto(t: String, tam: Float, color: Int, lineas: Int = 1) = TextView(this).apply {
        text = t
        textSize = tam
        setTextColor(getColor(color))
        maxLines = lineas
        ellipsize = TextUtils.TruncateAt.END
    }

    // ---------- videos ----------
    private fun cargarVideos() {
        val api = Api.de(this)
        Fondo.correr({ Pair(api.videos(), api.estado()) }, { (lista, est) ->
            videos = lista
            val listos = est.optInt("listos")
            val bajando = est.optString("bajando").takeIf { it.isNotEmpty() && it != "null" }
            estado.text = buildString {
                append("$listos listos · ${est.optDouble("gb_usados")} de ${est.optDouble("gb_max")} GB")
                if (bajando != null) append(" · bajando: $bajando (${est.optInt("progreso")}%)")
            }
            pintarVideos(lista)
        }, {
            estado.text = "Sin conexión con el servidor en ${api.base}"
            pintarVideos(emptyList())
        })
    }

    private fun pintarVideos(lista: List<Video>) {
        val fila = filaVideos ?: return
        val enfocado = fila.focusedChild?.tag
        fila.removeAllViews()
        if (lista.isEmpty()) {
            fila.addView(tarjetaSimple("Todavía no hay videos.\nRevisa Ajustes de YoTV.", null) {
                startActivity(Intent(this, AjustesActivity::class.java))
            })
            return
        }
        lista.forEachIndexed { i, v -> fila.addView(tarjetaVideo(v, i)) }
        if (enfocado != null) fila.findViewWithTag<View>(enfocado)?.requestFocus()
        else if (currentFocus == null) fila.getChildAt(0)?.requestFocus()
    }

    private fun tarjetaVideo(v: Video, indice: Int): View {
        val ancho = dp(256)
        val tarjeta = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            tag = v.id
            isFocusable = true
            setBackgroundResource(R.drawable.tarjeta)
            setPadding(dp(6), dp(6), dp(6), dp(8))
            layoutParams = LinearLayout.LayoutParams(ancho + dp(12), ViewGroup.LayoutParams.WRAP_CONTENT)
                .apply { marginEnd = dp(16) }
        }
        val marco = FrameLayout(this)
        val mini = ImageView(this).apply {
            scaleType = ImageView.ScaleType.CENTER_CROP
            setImageDrawable(ColorDrawable(Color.DKGRAY))
        }
        marco.addView(mini, FrameLayout.LayoutParams(ancho, ancho * 9 / 16))
        v.miniatura?.let { Fondo.imagen(Api.de(this).url(it), mini) }
        marco.addView(texto(duracion(v.duracion), 13f, R.color.texto).apply {
            setBackgroundColor(0xCC000000.toInt())
            setPadding(dp(6), dp(2), dp(6), dp(2))
        }, FrameLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT,
            Gravity.BOTTOM or Gravity.END).apply { setMargins(0, 0, dp(6), dp(6)) })
        if (v.posicion > 0 && v.duracion > 0) {
            val barra = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
                max = v.duracion
                progress = v.posicion
                progressTintList = android.content.res.ColorStateList.valueOf(getColor(R.color.acento))
            }
            marco.addView(barra, FrameLayout.LayoutParams(ancho, dp(4), Gravity.BOTTOM))
        }
        tarjeta.addView(marco)
        tarjeta.addView(texto(v.titulo, 15f, R.color.texto, 2).apply { setPadding(0, dp(6), 0, 0) })
        tarjeta.addView(texto(if (v.visto) "Ya lo viste · ${v.canal}" else v.canal, 13f, R.color.texto_suave))
        if (v.motivo.isNotEmpty()) tarjeta.addView(texto(v.motivo, 12f, R.color.texto_suave))

        alEnfocar(tarjeta)
        tarjeta.setOnClickListener { reproducir(indice) }
        tarjeta.setOnLongClickListener { opciones(v); true }
        return tarjeta
    }

    private fun duracion(seg: Int): String = when {
        seg <= 0 -> ""
        seg >= 3600 -> "%d:%02d:%02d".format(seg / 3600, seg % 3600 / 60, seg % 60)
        else -> "%d:%02d".format(seg / 60, seg % 60)
    }

    private fun reproducir(indice: Int) {
        startActivity(Intent(this, ReproductorActivity::class.java).apply {
            putExtra("ids", videos.map { it.id }.toTypedArray())
            putExtra("titulos", videos.map { it.titulo }.toTypedArray())
            putExtra("medias", videos.map { it.media }.toTypedArray())
            putExtra("posiciones", videos.map { it.posicion }.toIntArray())
            putExtra("duraciones", videos.map { it.duracion }.toIntArray())
            putExtra("indice", indice)
        })
    }

    private fun opciones(v: Video) {
        AlertDialog.Builder(this)
            .setTitle(v.titulo)
            .setItems(arrayOf("♥ Me gusta (más como este)", "✗ No me gusta (borrar)", "Cancelar")) { _, cual ->
                val op = when (cual) { 0 -> "me_gusta"; 1 -> "no_me_gusta"; else -> return@setItems }
                Fondo.correr({ Api.de(this).opinion(v.id, op) },
                    { aviso(if (op == "me_gusta") "Anotado" else "Borrado"); cargarVideos() },
                    { aviso("No hay conexión con el servidor") })
            }
            .show()
    }

    // ---------- apps instaladas ----------
    private fun cargarApps(fila: LinearLayout) {
        val pm = packageManager
        val intento = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LEANBACK_LAUNCHER)
        val apps = pm.queryIntentActivities(intento, 0)
            .filter { it.activityInfo.packageName != packageName }
            .sortedBy { it.loadLabel(pm).toString().lowercase() }
        for (app in apps) {
            val paquete = app.activityInfo.packageName
            val dibujo = app.activityInfo.loadBanner(pm) ?: app.activityInfo.applicationInfo.loadBanner(pm)
            fila.addView(tarjetaSimple(app.loadLabel(pm).toString(), dibujo ?: app.loadIcon(pm), dibujo != null) {
                val abrir = pm.getLeanbackLaunchIntentForPackage(paquete) ?: pm.getLaunchIntentForPackage(paquete)
                if (abrir != null) startActivity(abrir) else aviso("No se puede abrir")
            })
        }
    }

    private fun tarjetaSimple(titulo: String, imagen: Drawable?, esBanner: Boolean = false, alPulsar: () -> Unit): View {
        val tarjeta = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            isFocusable = true
            setBackgroundResource(R.drawable.tarjeta)
            setPadding(dp(8), dp(8), dp(8), dp(8))
            layoutParams = LinearLayout.LayoutParams(dp(176), dp(118)).apply { marginEnd = dp(16) }
        }
        if (imagen != null) {
            tarjeta.addView(ImageView(this).apply {
                setImageDrawable(imagen)
                scaleType = ImageView.ScaleType.FIT_CENTER
            }, LinearLayout.LayoutParams(if (esBanner) dp(160) else dp(56), if (esBanner) dp(90) else dp(56)))
        }
        if (!esBanner) {
            tarjeta.addView(texto(titulo, 14f, R.color.texto, 3).apply { gravity = Gravity.CENTER })
        }
        alEnfocar(tarjeta)
        tarjeta.setOnClickListener { alPulsar() }
        return tarjeta
    }

    private fun aviso(t: String) = Toast.makeText(this, t, Toast.LENGTH_SHORT).show()
}
