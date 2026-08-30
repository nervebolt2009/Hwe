package com.example.ui.viewmodel

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * SLEEP TIMER: pauses playback after [minutes], fading volume to zero over
 * the final 10 seconds. minutes <= 0 cancels an active timer.
 */
class SleepTimerController(
    private val scope: CoroutineScope,
    private val setVolume: (Float) -> Unit,
    private val pause: () -> Unit
) {

    private var job: Job? = null

    private val _remainingMs = MutableStateFlow(0L)
    val remainingMs: StateFlow<Long> = _remainingMs.asStateFlow()

    fun set(minutes: Int) {
        job?.cancel()
        setVolume(1f)
        if (minutes <= 0) {
            _remainingMs.value = 0L
            return
        }
        val durationMs = minutes * 60_000L
        val endsAt = System.currentTimeMillis() + durationMs
        job = scope.launch {
            var lastTick = System.nanoTime()
            while (true) {
                delay(250)
                val now = System.currentTimeMillis()
                val remaining = endsAt - now
                _remainingMs.value = remaining.coerceAtLeast(0L)
                if (remaining <= 10_000L) {
                    // Fade over the final 10 seconds.
                    val nowNano = System.nanoTime()
                    val dtSec = ((nowNano - lastTick) / 1_000_000_000f).coerceIn(0.05f, 0.5f)
                    lastTick = nowNano
                    val step = dtSec / 10f
                    val currentVol = 1f - ((10_000f - remaining.toFloat()) / 10_000f)
                    setVolume((currentVol - step).coerceIn(0f, 1f))
                }
                if (remaining <= 0L) break
            }
            pause()
            setVolume(1f)
            _remainingMs.value = 0L
        }
    }
}
