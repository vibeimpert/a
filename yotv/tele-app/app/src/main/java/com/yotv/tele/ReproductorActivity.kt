package com.yotv.tele

import android.app.Activity
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.view.WindowManager
import android.widget.TextView
import androidx.annotation.OptIn
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.DefaultHttpDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.MergingMediaSource
import androidx.media3.exoplayer.source.ProgressiveMediaSource
import androidx.media3.ui.PlayerView

/** Reproduce los videos guardados uno tras otro y le cuenta al servidor hasta dónde viste.
 *  Puede reproducir un video que todavía se está bajando: el servidor espera los bytes que faltan. */
@OptIn(UnstableApi::class)
class ReproductorActivity : Activity() {
    private lateinit var reproductor: ExoPlayer
    private lateinit var titulo: TextView
    private lateinit var api: Api
    private lateinit var ids: Array<String>
    private lateinit var titulos: Array<String>
    private lateinit var medias: Array<String>
    private lateinit var audios: Array<String>
    private lateinit var fuentes: ProgressiveMediaSource.Factory
    private lateinit var posiciones: IntArray
    private lateinit var duraciones: IntArray
    private var actual = 0
    private val reloj = Handler(Looper.getMainLooper())
    private val reportarCada = object : Runnable {
        override fun run() {
            reportar()
            reloj.postDelayed(this, 15_000)
        }
    }
    private val ocultarTitulo = Runnable { titulo.visibility = View.GONE }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_reproductor)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        api = Api.de(this)
        ids = intent.getStringArrayExtra("ids") ?: emptyArray()
        titulos = intent.getStringArrayExtra("titulos") ?: emptyArray()
        medias = intent.getStringArrayExtra("medias") ?: emptyArray()
        audios = intent.getStringArrayExtra("audios") ?: Array(medias.size) { "" }
        // Lectura con paciencia: si alcanzas a la descarga, el servidor tarda en mandar lo que falta.
        fuentes = ProgressiveMediaSource.Factory(
            DefaultHttpDataSource.Factory().setConnectTimeoutMs(8_000).setReadTimeoutMs(60_000))
        posiciones = intent.getIntArrayExtra("posiciones") ?: IntArray(0)
        duraciones = intent.getIntArrayExtra("duraciones") ?: IntArray(0)
        actual = intent.getIntExtra("indice", 0)
        if (actual !in ids.indices) { finish(); return }

        titulo = findViewById(R.id.titulo)
        reproductor = ExoPlayer.Builder(this).setSeekBackIncrementMs(10_000).setSeekForwardIncrementMs(30_000).build()
        findViewById<PlayerView>(R.id.pantalla).player = reproductor
        reproductor.addListener(object : Player.Listener {
            override fun onPlaybackStateChanged(estado: Int) {
                if (estado == Player.STATE_ENDED) siguiente()
            }
        })
        cargar(actual)
    }

    private fun cargar(i: Int) {
        actual = i
        val video = fuentes.createMediaSource(MediaItem.fromUri(api.url(medias[i])))
        reproductor.setMediaSource(
            if (audios[i].isEmpty()) video
            else MergingMediaSource(video, fuentes.createMediaSource(MediaItem.fromUri(api.url(audios[i]))))
        )
        val pos = posiciones[i]
        val dur = duraciones[i]
        // Sigue donde lo dejaste, salvo que ya lo hayas terminado.
        if (pos > 10 && (dur == 0 || pos < dur * 0.9)) reproductor.seekTo(pos * 1000L)
        reproductor.prepare()
        reproductor.play()
        titulo.text = titulos[i]
        titulo.visibility = View.VISIBLE
        reloj.removeCallbacks(ocultarTitulo)
        reloj.postDelayed(ocultarTitulo, 5000)
    }

    private fun reportar(terminado: Boolean = false) {
        if (!::reproductor.isInitialized || actual !in ids.indices) return
        val dur = (reproductor.duration.takeIf { it > 0 } ?: (duraciones[actual] * 1000L)) / 1000
        val pos = if (terminado) dur else reproductor.currentPosition / 1000
        if (pos <= 0) return
        val id = ids[actual]
        posiciones[actual] = pos.toInt()
        Fondo.correr({ api.progreso(id, pos.toInt(), dur.toInt()) }, {})
    }

    private fun siguiente() {
        reportar(terminado = true)
        if (actual + 1 < ids.size) cargar(actual + 1) else finish()
    }

    override fun onStart() {
        super.onStart()
        reloj.postDelayed(reportarCada, 15_000)
    }

    override fun onStop() {
        super.onStop()
        reloj.removeCallbacks(reportarCada)
        reportar()
        if (::reproductor.isInitialized) reproductor.pause()
    }

    override fun onDestroy() {
        super.onDestroy()
        reloj.removeCallbacksAndMessages(null)
        if (::reproductor.isInitialized) reproductor.release()
    }
}
