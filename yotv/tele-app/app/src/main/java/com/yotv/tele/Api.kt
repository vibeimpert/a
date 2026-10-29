package com.yotv.tele

import android.content.Context
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

data class Video(
    val id: String,
    val titulo: String,
    val canal: String,
    val duracion: Int,
    val posicion: Int,
    val motivo: String,
    val visto: Boolean,
    val media: String,
    val miniatura: String?,
)

/** Habla con el servidor YoTV (en la propia tele vía Termux, en la PS4 o en tu compu). */
class Api(base: String) {
    val base = base.trimEnd('/')

    fun url(ruta: String) = base + ruta

    private fun pedir(ruta: String, metodo: String = "GET", cuerpo: JSONObject? = null): String {
        val con = URL(url(ruta)).openConnection() as HttpURLConnection
        con.connectTimeout = 4000
        con.readTimeout = 8000
        con.requestMethod = metodo
        if (cuerpo != null) {
            con.doOutput = true
            con.setRequestProperty("Content-Type", "application/json")
            con.outputStream.use { it.write(cuerpo.toString().toByteArray()) }
        }
        try {
            if (con.responseCode !in 200..299) error("El servidor respondió ${con.responseCode}")
            return con.inputStream.bufferedReader().use { it.readText() }
        } finally {
            con.disconnect()
        }
    }

    fun videos(): List<Video> {
        val lista = JSONObject(pedir("/api/videos")).getJSONArray("videos")
        return (0 until lista.length()).map { i ->
            val v = lista.getJSONObject(i)
            Video(
                id = v.getString("id"),
                titulo = v.getString("titulo"),
                canal = v.optString("canal", ""),
                duracion = v.optInt("duracion", 0),
                posicion = v.optInt("posicion", 0),
                motivo = v.optString("motivo", ""),
                visto = v.optBoolean("visto", false),
                media = v.getString("media"),
                miniatura = if (v.isNull("miniatura")) null else v.getString("miniatura"),
            )
        }
    }

    fun estado(): JSONObject = JSONObject(pedir("/api/estado"))

    fun progreso(id: String, posicion: Int, duracion: Int) {
        pedir("/api/videos/$id/progreso", "POST",
            JSONObject().put("posicion", posicion).put("duracion", duracion))
    }

    fun opinion(id: String, opinion: String) {
        pedir("/api/videos/$id/opinion", "POST", JSONObject().put("opinion", opinion))
    }

    fun actualizar() {
        pedir("/api/actualizar", "POST", JSONObject())
    }

    companion object {
        private const val PREFS = "yotv"
        const val POR_DEFECTO = "http://127.0.0.1:8765"

        fun servidor(ctx: Context): String =
            ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString("servidor", POR_DEFECTO)!!

        fun guardarServidor(ctx: Context, url: String) {
            ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putString("servidor", url).apply()
        }

        fun de(ctx: Context) = Api(servidor(ctx))
    }
}
