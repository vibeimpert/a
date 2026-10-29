package com.yotv.tele

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.os.Handler
import android.os.Looper
import android.util.LruCache
import android.widget.ImageView
import java.net.URL
import java.util.concurrent.Executors

/** Hilos en segundo plano para la red y carga de miniaturas con caché en memoria. */
object Fondo {
    private val hilos = Executors.newFixedThreadPool(4)
    private val principal = Handler(Looper.getMainLooper())
    private val cache = object : LruCache<String, Bitmap>(24 * 1024 * 1024) {
        override fun sizeOf(key: String, value: Bitmap) = value.byteCount
    }

    fun <T> correr(trabajo: () -> T, listo: (T) -> Unit, error: (Exception) -> Unit = {}) {
        hilos.execute {
            try {
                val r = trabajo()
                principal.post { listo(r) }
            } catch (e: Exception) {
                principal.post { error(e) }
            }
        }
    }

    fun imagen(url: String, destino: ImageView) {
        destino.tag = url
        cache.get(url)?.let { destino.setImageBitmap(it); return }
        correr({
            val opciones = BitmapFactory.Options().apply { inSampleSize = 2 }
            URL(url).openStream().use { BitmapFactory.decodeStream(it, null, opciones) }
        }, { bmp ->
            if (bmp != null) {
                cache.put(url, bmp)
                if (destino.tag == url) destino.setImageBitmap(bmp)
            }
        })
    }
}
