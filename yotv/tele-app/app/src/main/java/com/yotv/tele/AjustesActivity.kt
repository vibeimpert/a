package com.yotv.tele

import android.app.Activity
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.TextView

/** Aquí se escribe la dirección del servidor YoTV. */
class AjustesActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_ajustes)
        val campo = findViewById<EditText>(R.id.servidor)
        val resultado = findViewById<TextView>(R.id.resultado)
        campo.setText(Api.servidor(this))

        findViewById<Button>(R.id.guardar).setOnClickListener {
            var url = campo.text.toString().trim()
            if (!url.startsWith("http")) url = "http://$url"
            if (!Regex(":\\d+/?$").containsMatchIn(url)) url = url.trimEnd('/') + ":8765"
            campo.setText(url)
            resultado.text = "Probando…"
            Fondo.correr({ Api(url).estado() }, { est ->
                Api.guardarServidor(this, url)
                resultado.text = "✓ Conectado. ${est.optInt("listos")} videos listos, " +
                    "Claude: ${if (est.optBoolean("con_claude")) "sí" else "no"}. Guardado."
            }, { e ->
                resultado.text = "✗ No pude conectar (${e.message}). Revisa que el servidor esté prendido."
            })
        }
    }
}
