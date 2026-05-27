package com.swarm.seven

import android.opengl.EGL14
import android.opengl.EGLConfig
import android.opengl.GLES20
import org.json.JSONObject
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.FloatBuffer
import kotlin.math.max

object GpuProbe {
    fun run(modelSize: Int = 4, benchmarkSizes: List<Int> = emptyList(), capsule: JSONObject? = null): JSONObject {
        val started = System.nanoTime()
        val display = EGL14.eglGetDisplay(EGL14.EGL_DEFAULT_DISPLAY)
        if (display == EGL14.EGL_NO_DISPLAY) return failure("no EGL display")
        val version = IntArray(2)
        if (!EGL14.eglInitialize(display, version, 0, version, 1)) return failure("eglInitialize failed")
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
                display, config, EGL14.EGL_NO_CONTEXT,
                intArrayOf(EGL14.EGL_CONTEXT_CLIENT_VERSION, 2, EGL14.EGL_NONE), 0,
            )
            if (context == EGL14.EGL_NO_CONTEXT) return failure("eglCreateContext failed")
            surface = EGL14.eglCreatePbufferSurface(
                display, config,
                intArrayOf(EGL14.EGL_WIDTH, 16, EGL14.EGL_HEIGHT, 16, EGL14.EGL_NONE), 0,
            )
            if (surface == EGL14.EGL_NO_SURFACE) return failure("eglCreatePbufferSurface failed")
            if (!EGL14.eglMakeCurrent(display, surface, surface, context)) return failure("eglMakeCurrent failed")

            val vendor = GLES20.glGetString(GLES20.GL_VENDOR) ?: "unknown"
            val renderer = GLES20.glGetString(GLES20.GL_RENDERER) ?: "unknown"
            val glVersion = GLES20.glGetString(GLES20.GL_VERSION) ?: "unknown"
            GLES20.glViewport(0, 0, 16, 16)
            val shaderStart = System.nanoTime()
            repeat(120) { i ->
                val r = (i % 16) / 15.0f
                GLES20.glClearColor(r, 0.35f, 0.72f, 1.0f)
                GLES20.glClear(GLES20.GL_COLOR_BUFFER_BIT)
            }
            val sizes = benchmarkSizes.ifEmpty { listOf(modelSize) }
                .map { it.coerceIn(4, 128) }
                .distinct()
            val models = sizes.map { runTinyGpuModel(it) }
            val tinyModel = models.last()
            val capsuleResult = capsule?.let { runModelCapsule(it) }
            GLES20.glFinish()
            val shaderMs = (System.nanoTime() - shaderStart) / 1_000_000.0
            val totalMs = (System.nanoTime() - started) / 1_000_000.0
            val error = GLES20.glGetError()
            JSONObject().apply {
                put("ok", error == GLES20.GL_NO_ERROR && tinyModel.optBoolean("ok", false) && (capsuleResult?.optBoolean("ok", true) ?: true))
                put("probe", "gles-pbuffer-clear")
                put("iterations", 120)
                put("shader_ms", round1(shaderMs))
                put("total_ms", round1(totalMs))
                put("vendor", vendor)
                put("renderer", renderer)
                put("gl_version", glVersion)
                put("gl_error", error)
                put("tiny_model", tinyModel)
                capsuleResult?.let { put("model_capsule", it) }
                if (models.size > 1) {
                    put("benchmark_ladder", org.json.JSONArray().also { arr ->
                        models.forEach { arr.put(it) }
                    })
                    put("capacity_score", capacityScore(models))
                }
            }
        } catch (e: Exception) {
            failure(e.javaClass.simpleName + ": " + (e.message ?: "unknown"))
        } finally {
            if (display != EGL14.EGL_NO_DISPLAY) {
                EGL14.eglMakeCurrent(display, EGL14.EGL_NO_SURFACE, EGL14.EGL_NO_SURFACE, EGL14.EGL_NO_CONTEXT)
                if (surface != EGL14.EGL_NO_SURFACE) EGL14.eglDestroySurface(display, surface)
                if (context != EGL14.EGL_NO_CONTEXT) EGL14.eglDestroyContext(display, context)
                EGL14.eglTerminate(display)
            }
        }
    }

    private fun failure(error: String): JSONObject = JSONObject().apply {
        put("ok", false)
        put("probe", "gles-pbuffer-clear")
        put("error", error)
    }

    private fun round1(value: Double): Double = max(0.0, Math.round(value * 10.0) / 10.0)

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
                void main() {
                  gl_Position = vec4(aPos, 0.0, 1.0);
                }
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
            val input = floatArrayOf(0.18f, 0.41f, 0.73f, 1.0f)
            val weights = floatArrayOf(
                0.62f, 0.10f, 0.24f, 0.02f,
                0.12f, 0.58f, 0.16f, 0.04f,
                0.08f, 0.18f, 0.70f, 0.02f,
                0.20f, 0.14f, 0.18f, 0.48f,
            )
            GLES20.glUniform4fv(GLES20.glGetUniformLocation(program, "uInput"), 1, input, 0)
            GLES20.glUniformMatrix4fv(GLES20.glGetUniformLocation(program, "uWeights"), 1, false, weights, 0)
            val vertices = floatBuffer(floatArrayOf(-1f, -1f, 1f, -1f, -1f, 1f, 1f, 1f))
            GLES20.glEnableVertexAttribArray(pos)
            GLES20.glVertexAttribPointer(pos, 2, GLES20.GL_FLOAT, false, 0, vertices)
            val tiles = ((modelSize * modelSize) / 16).coerceAtLeast(1)
            repeat(tiles) { GLES20.glDrawArrays(GLES20.GL_TRIANGLE_STRIP, 0, 4) }
            val pixel = ByteBuffer.allocateDirect(4)
            GLES20.glReadPixels(0, 0, 1, 1, GLES20.GL_RGBA, GLES20.GL_UNSIGNED_BYTE, pixel)
            val elapsedMs = (System.nanoTime() - started) / 1_000_000.0
            val err = GLES20.glGetError()
            JSONObject().apply {
                put("ok", err == GLES20.GL_NO_ERROR)
                put("model", "tiny-gpu-linear-${modelSize}x$modelSize")
                put("model_size", modelSize)
                put("delegate", "gles-fragment-shader")
                put("tiles", tiles)
                put("weights_loaded", modelSize * modelSize)
                put("input_features", modelSize)
                put("output_rgba", org.json.JSONArray().also { arr ->
                    repeat(4) { arr.put(pixel.get(it).toInt() and 0xff) }
                })
                put("latency_ms", round1(elapsedMs))
                put("gl_error", err)
            }
        } finally {
            GLES20.glDeleteProgram(program)
        }
    }

    private fun runModelCapsule(capsule: JSONObject): JSONObject {
        val started = System.nanoTime()
        val capsuleId = capsule.optString("capsule_id", "swarm-capsule")
        val input = floatArrayFromJson(capsule.optJSONArray("input"), floatArrayOf(0.18f, 0.41f, 0.73f, 1.0f), 4)
        val weights = floatArrayFromJson(capsule.optJSONArray("weights"), floatArrayOf(
            0.62f, 0.10f, 0.24f, 0.02f,
            0.12f, 0.58f, 0.16f, 0.04f,
            0.08f, 0.18f, 0.70f, 0.02f,
            0.20f, 0.14f, 0.18f, 0.48f,
        ), 16)
        val program = linkProgram(
            vertexSource = """
                attribute vec2 aPos;
                void main() {
                  gl_Position = vec4(aPos, 0.0, 1.0);
                }
            """.trimIndent(),
            fragmentSource = """
                precision mediump float;
                uniform vec4 uInput;
                uniform mat4 uWeights;
                void main() {
                  vec4 logits = uWeights * uInput;
                  float y = clamp(logits.r + logits.g - logits.b * 0.5 + logits.a * 0.25, 0.0, 1.0);
                  gl_FragColor = vec4(y, clamp(logits.g, 0.0, 1.0), clamp(1.0 - y, 0.0, 1.0), 1.0);
                }
            """.trimIndent(),
        )
        return try {
            GLES20.glUseProgram(program)
            val pos = GLES20.glGetAttribLocation(program, "aPos")
            GLES20.glUniform4fv(GLES20.glGetUniformLocation(program, "uInput"), 1, input, 0)
            GLES20.glUniformMatrix4fv(GLES20.glGetUniformLocation(program, "uWeights"), 1, false, weights, 0)
            val vertices = floatBuffer(floatArrayOf(-1f, -1f, 1f, -1f, -1f, 1f, 1f, 1f))
            GLES20.glEnableVertexAttribArray(pos)
            GLES20.glVertexAttribPointer(pos, 2, GLES20.GL_FLOAT, false, 0, vertices)
            GLES20.glDrawArrays(GLES20.GL_TRIANGLE_STRIP, 0, 4)
            val pixel = ByteBuffer.allocateDirect(4)
            GLES20.glReadPixels(0, 0, 1, 1, GLES20.GL_RGBA, GLES20.GL_UNSIGNED_BYTE, pixel)
            val err = GLES20.glGetError()
            JSONObject().apply {
                put("ok", err == GLES20.GL_NO_ERROR)
                put("capsule_id", capsuleId)
                put("model", capsule.optString("model", "swarm-linear-4x4"))
                put("delegate", "gles-fragment-shader")
                put("source", "hive-payload")
                put("weights_loaded", weights.size)
                put("input_features", input.size)
                put("output_rgba", org.json.JSONArray().also { arr ->
                    repeat(4) { arr.put(pixel.get(it).toInt() and 0xff) }
                })
                put("latency_ms", round1((System.nanoTime() - started) / 1_000_000.0))
                put("gl_error", err)
            }
        } finally {
            GLES20.glDeleteProgram(program)
        }
    }

    private fun floatArrayFromJson(values: org.json.JSONArray?, fallback: FloatArray, expected: Int): FloatArray {
        if (values == null || values.length() != expected) return fallback
        return FloatArray(expected) { idx -> values.optDouble(idx, fallback[idx].toDouble()).toFloat() }
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
        GLES20.glDeleteShader(vertex)
        GLES20.glDeleteShader(fragment)
        if (status[0] == 0) {
            val log = GLES20.glGetProgramInfoLog(program)
            GLES20.glDeleteProgram(program)
            throw IllegalStateException("GPU model link failed: $log")
        }
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
            throw IllegalStateException("GPU model compile failed: $log")
        }
        return shader
    }

    private fun floatBuffer(values: FloatArray): FloatBuffer = ByteBuffer
        .allocateDirect(values.size * 4)
        .order(ByteOrder.nativeOrder())
        .asFloatBuffer()
        .apply {
            put(values)
            position(0)
        }
}