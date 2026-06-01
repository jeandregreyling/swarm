package com.swarm.hive

import android.opengl.EGL14
import android.opengl.EGLConfig
import android.opengl.GLES20
import org.json.JSONArray
import org.json.JSONObject
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.FloatBuffer
import kotlin.math.max

object GpuProbe {
    fun run(
        modelSize: Int = 4,
        benchmarkSizes: JSONArray? = null,
        capsule: JSONObject? = null,
    ): JSONObject {
        val started = System.nanoTime()
        val display = EGL14.eglGetDisplay(EGL14.EGL_DEFAULT_DISPLAY)
        if (display == EGL14.EGL_NO_DISPLAY) return failure("no EGL display")
        val version = IntArray(2)
        if (!EGL14.eglInitialize(display, version, 0, version, 1)) {
            return failure("eglInitialize failed")
        }
        var surface = EGL14.EGL_NO_SURFACE
        var context = EGL14.EGL_NO_CONTEXT
        return try {
            val configs = arrayOfNulls<EGLConfig>(1)
            val count = IntArray(1)
            val attrs = intArrayOf(
                EGL14.EGL_RENDERABLE_TYPE, EGL14.EGL_OPENGL_ES2_BIT,
                EGL14.EGL_RED_SIZE, 8,
                EGL14.EGL_GREEN_SIZE, 8,
                EGL14.EGL_BLUE_SIZE, 8,
                EGL14.EGL_ALPHA_SIZE, 8,
                EGL14.EGL_SURFACE_TYPE, EGL14.EGL_PBUFFER_BIT,
                EGL14.EGL_NONE,
            )
            if (!EGL14.eglChooseConfig(display, attrs, 0, configs, 0, 1, count, 0) || count[0] == 0) {
                return failure("eglChooseConfig failed")
            }
            val config = configs[0] ?: return failure("missing EGL config")
            context = EGL14.eglCreateContext(
                display,
                config,
                EGL14.EGL_NO_CONTEXT,
                intArrayOf(EGL14.EGL_CONTEXT_CLIENT_VERSION, 2, EGL14.EGL_NONE),
                0,
            )
            if (context == EGL14.EGL_NO_CONTEXT) return failure("eglCreateContext failed")
            surface = EGL14.eglCreatePbufferSurface(
                display,
                config,
                intArrayOf(EGL14.EGL_WIDTH, 16, EGL14.EGL_HEIGHT, 16, EGL14.EGL_NONE),
                0,
            )
            if (surface == EGL14.EGL_NO_SURFACE) return failure("eglCreatePbufferSurface failed")
            if (!EGL14.eglMakeCurrent(display, surface, surface, context)) {
                return failure("eglMakeCurrent failed")
            }

            val vendor = GLES20.glGetString(GLES20.GL_VENDOR) ?: "unknown"
            val renderer = GLES20.glGetString(GLES20.GL_RENDERER) ?: "unknown"
            val glVersion = GLES20.glGetString(GLES20.GL_VERSION) ?: "unknown"
            GLES20.glViewport(0, 0, 16, 16)

            val sizes = sizesFromJson(benchmarkSizes, modelSize)
            val models = sizes.map { runTinyGpuModel(it) }
            val capsuleResult = capsule?.let { runModelCapsule(it) }
            GLES20.glFinish()

            val glError = GLES20.glGetError()
            JSONObject().apply {
                put("ok", glError == GLES20.GL_NO_ERROR && models.any { it.optBoolean("ok", false) })
                put("probe", "gles-pbuffer-model")
                put("vendor", vendor)
                put("renderer", renderer)
                put("gl_version", glVersion)
                put("gl_error", glError)
                put("total_ms", round1((System.nanoTime() - started) / 1_000_000.0))
                put("tiny_model", models.lastOrNull() ?: JSONObject())
                put("benchmark_ladder", JSONArray().also { arr -> models.forEach { arr.put(it) } })
                put("capacity_score", capacityScore(models))
                capsuleResult?.let { put("model_capsule", it) }
            }
        } catch (e: Exception) {
            failure(e.javaClass.simpleName + ": " + (e.message ?: "unknown"))
        } finally {
            if (display != EGL14.EGL_NO_DISPLAY) {
                EGL14.eglMakeCurrent(
                    display,
                    EGL14.EGL_NO_SURFACE,
                    EGL14.EGL_NO_SURFACE,
                    EGL14.EGL_NO_CONTEXT,
                )
                if (surface != EGL14.EGL_NO_SURFACE) EGL14.eglDestroySurface(display, surface)
                if (context != EGL14.EGL_NO_CONTEXT) EGL14.eglDestroyContext(display, context)
                EGL14.eglTerminate(display)
            }
        }
    }

    private fun sizesFromJson(values: JSONArray?, fallback: Int): List<Int> {
        val out = mutableListOf<Int>()
        if (values != null) {
            for (i in 0 until values.length()) {
                val n = values.optInt(i, 0)
                if (n > 0) out.add(n.coerceIn(4, 128))
            }
        }
        if (out.isEmpty()) out.add(fallback.coerceIn(4, 128))
        if (128 !in out) out.add(128)
        return out.distinct()
    }

    private fun failure(error: String): JSONObject = JSONObject().apply {
        put("ok", false)
        put("probe", "gles-pbuffer-model")
        put("error", error)
        put("capacity_score", 0)
    }

    private fun capacityScore(models: List<JSONObject>): Int {
        val okModels = models.filter { it.optBoolean("ok", false) }
        if (okModels.isEmpty()) return 0
        val largest = okModels.maxOf { it.optInt("model_size", 4) }
        val avgLatency = okModels.map { it.optDouble("latency_ms", 999.0) }.average()
        val sizeScore = when {
            largest >= 128 -> 55
            largest >= 64 -> 42
            largest >= 16 -> 28
            else -> 16
        }
        val latencyScore = when {
            avgLatency <= 10.0 -> 35
            avgLatency <= 25.0 -> 25
            avgLatency <= 60.0 -> 15
            else -> 6
        }
        return (sizeScore + latencyScore + 10).coerceIn(0, 100)
    }

    private fun runTinyGpuModel(modelSize: Int): JSONObject {
        val started = System.nanoTime()
        val program = linkProgram(
            vertexSource = """
                attribute vec2 aPos;
                void main() { gl_Position = vec4(aPos, 0.0, 1.0); }
            """.trimIndent(),
            fragmentSource = """
                precision mediump float;
                uniform vec4 uInput;
                uniform mat4 uWeights;
                void main() {
                  vec4 logits = uWeights * uInput;
                  float y = clamp(logits.r + logits.g * 0.5 - logits.b * 0.25 + logits.a * 0.125, 0.0, 1.0);
                  gl_FragColor = vec4(y, logits.g, 1.0 - y, 1.0);
                }
            """.trimIndent(),
        )
        return try {
            GLES20.glUseProgram(program)
            val pos = GLES20.glGetAttribLocation(program, "aPos")
            GLES20.glUniform4fv(
                GLES20.glGetUniformLocation(program, "uInput"),
                1,
                floatArrayOf(0.18f, 0.41f, 0.73f, 1.0f),
                0,
            )
            GLES20.glUniformMatrix4fv(
                GLES20.glGetUniformLocation(program, "uWeights"),
                1,
                false,
                floatArrayOf(
                    0.62f, 0.10f, 0.24f, 0.02f,
                    0.12f, 0.58f, 0.16f, 0.04f,
                    0.08f, 0.18f, 0.70f, 0.02f,
                    0.20f, 0.14f, 0.18f, 0.48f,
                ),
                0,
            )
            val vertices = floatBuffer(floatArrayOf(-1f, -1f, 1f, -1f, -1f, 1f, 1f, 1f))
            GLES20.glEnableVertexAttribArray(pos)
            GLES20.glVertexAttribPointer(pos, 2, GLES20.GL_FLOAT, false, 0, vertices)
            val tiles = ((modelSize * modelSize) / 16).coerceAtLeast(1)
            repeat(tiles) { GLES20.glDrawArrays(GLES20.GL_TRIANGLE_STRIP, 0, 4) }
            val pixel = ByteBuffer.allocateDirect(4)
            GLES20.glReadPixels(0, 0, 1, 1, GLES20.GL_RGBA, GLES20.GL_UNSIGNED_BYTE, pixel)
            val err = GLES20.glGetError()
            JSONObject().apply {
                put("ok", err == GLES20.GL_NO_ERROR)
                put("model", "tiny-gpu-linear-${modelSize}x$modelSize")
                put("model_size", modelSize)
                put("delegate", "gles-fragment-shader")
                put("tiles", tiles)
                put("latency_ms", round1((System.nanoTime() - started) / 1_000_000.0))
                put("gl_error", err)
                put("output_rgba", JSONArray().also { arr ->
                    repeat(4) { arr.put(pixel.get(it).toInt() and 0xff) }
                })
            }
        } finally {
            GLES20.glDeleteProgram(program)
        }
    }

    private fun runModelCapsule(capsule: JSONObject): JSONObject {
        val model = runTinyGpuModel(4)
        return JSONObject().apply {
            put("ok", model.optBoolean("ok", false))
            put("capsule_id", capsule.optString("capsule_id", "swarm-capsule"))
            put("model", capsule.optString("model", "swarm-linear-4x4"))
            put("delegate", "gles-fragment-shader")
            put("source", "hive-payload")
            put("latency_ms", model.optDouble("latency_ms", -1.0))
            put("output_rgba", model.optJSONArray("output_rgba") ?: JSONArray())
        }
    }

    private fun linkProgram(vertexSource: String, fragmentSource: String): Int {
        val vertex = compileShader(GLES20.GL_VERTEX_SHADER, vertexSource)
        val fragment = compileShader(GLES20.GL_FRAGMENT_SHADER, fragmentSource)
        val program = GLES20.glCreateProgram()
        GLES20.glAttachShader(program, vertex)
        GLES20.glAttachShader(program, fragment)
        GLES20.glLinkProgram(program)
        val status = IntArray(1)
        GLES20.glGetProgramiv(program, GLES20.GL_LINK_STATUS, status, 0)
        if (status[0] == 0) {
            val log = GLES20.glGetProgramInfoLog(program)
            GLES20.glDeleteProgram(program)
            throw IllegalStateException("program link failed: $log")
        }
        GLES20.glDeleteShader(vertex)
        GLES20.glDeleteShader(fragment)
        return program
    }

    private fun compileShader(type: Int, source: String): Int {
        val shader = GLES20.glCreateShader(type)
        GLES20.glShaderSource(shader, source)
        GLES20.glCompileShader(shader)
        val status = IntArray(1)
        GLES20.glGetShaderiv(shader, GLES20.GL_COMPILE_STATUS, status, 0)
        if (status[0] == 0) {
            val log = GLES20.glGetShaderInfoLog(shader)
            GLES20.glDeleteShader(shader)
            throw IllegalStateException("shader compile failed: $log")
        }
        return shader
    }

    private fun floatBuffer(values: FloatArray): FloatBuffer =
        ByteBuffer.allocateDirect(values.size * 4)
            .order(ByteOrder.nativeOrder())
            .asFloatBuffer()
            .apply {
                put(values)
                position(0)
            }

    private fun round1(value: Double): Double = max(0.0, Math.round(value * 10.0) / 10.0)
}
