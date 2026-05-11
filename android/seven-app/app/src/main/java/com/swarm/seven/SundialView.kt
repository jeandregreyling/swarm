package com.swarm.seven

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.View
import kotlin.math.min

/** Compact at-a-glance system status dial for the Seven Android app. */
class SundialView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0,
) : View(context, attrs, defStyleAttr) {
    private val bgPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 18f
        strokeCap = Paint.Cap.ROUND
        color = Color.rgb(45, 55, 72)
    }
    private val arcPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 18f
        strokeCap = Paint.Cap.ROUND
        color = Color.rgb(79, 209, 197)
    }
    private val titlePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(224, 230, 241)
        textAlign = Paint.Align.CENTER
        textSize = 34f
        isFakeBoldText = true
    }
    private val subPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(160, 174, 192)
        textAlign = Paint.Align.CENTER
        textSize = 20f
    }

    private var score = 0
    private var label = "Checking"
    private var subtitle = "Leader · Potato · Resources"

    fun setStatus(score: Int, label: String, subtitle: String) {
        this.score = score.coerceIn(0, 100)
        this.label = label
        this.subtitle = subtitle
        arcPaint.color = when {
            this.score >= 80 -> Color.rgb(79, 209, 197)
            this.score >= 55 -> Color.rgb(246, 173, 85)
            else -> Color.rgb(245, 101, 101)
        }
        invalidate()
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val desired = 190
        val w = resolveSize(desired, widthMeasureSpec)
        val h = resolveSize(desired, heightMeasureSpec)
        setMeasuredDimension(w, h)
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val size = min(width, height).toFloat()
        val pad = 28f
        val rect = RectF(
            (width - size) / 2f + pad,
            (height - size) / 2f + pad,
            (width + size) / 2f - pad,
            (height + size) / 2f - pad,
        )
        canvas.drawArc(rect, 140f, 260f, false, bgPaint)
        canvas.drawArc(rect, 140f, 260f * score / 100f, false, arcPaint)
        canvas.drawText("$score%", width / 2f, height / 2f - 8f, titlePaint)
        canvas.drawText(label, width / 2f, height / 2f + 24f, subPaint)
        canvas.drawText(subtitle, width / 2f, height - 18f, subPaint)
    }
}