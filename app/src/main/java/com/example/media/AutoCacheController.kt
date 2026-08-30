package com.example.media

import android.content.Context
import android.net.ConnectivityManager
import com.example.data.WearsicRecentRepository
import com.example.data.db.WearsicDownloadEntity
import com.example.model.PlaybackUiState
import com.example.model.Track
import com.example.media.download.WearsicDownloadManager
import com.example.network.WearsicHttp
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import okhttp3.Request
import java.util.concurrent.TimeUnit

/**
 * GUARANTEED offline layer: every streamed song that starts playing is
 * immediately saved as a real download (subject to the Auto-Cache toggle,
 * network availability and the offline cap). This replaces reliance on
 * ExoPlayer's opaque stream cache — play a song once online and it plays
 * forever offline. The NEXT queued track is also pre-warmed on the server
 * to kill extraction delay.
 *
 * Extracted from WearsicPlayerViewModel to keep the ViewModel focused on UI
 * state; this controller owns the background auto-cache + warm-up behavior.
 */
class AutoCacheController(
    private val context: Context,
    private val scope: CoroutineScope,
    private val downloadManager: WearsicDownloadManager,
    private val downloads: StateFlow<List<WearsicDownloadEntity>>,
    private val autoCacheEnabled: StateFlow<Boolean>,
    private val recentRepository: WearsicRecentRepository
) {

    private val appContext = context.applicationContext

    // Lightweight client used only to pre-warm the server's stream cache for
    // the NEXT track in the queue, so it starts playing instantly.
    private val warmUpClient = WearsicHttp.client.newBuilder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .build()

    @Volatile
    private var lastWarmUpTrackId: String? = null

    fun attach(playbackState: StateFlow<PlaybackUiState>) {
        scope.launch {
            val autoCachedTrackIds = mutableSetOf<String>()
            var lastTrack: Track? = null

            playbackState.collect { state ->
                val track = state.currentTrack
                if (track.id.isNotBlank()) {
                    if (track.id != lastTrack?.id) {
                        // Track changed: save the previous one if mid-play.
                        lastTrack?.let { previous ->
                            maybeAutoCacheTrack(previous, autoCachedTrackIds)
                        }
                        lastTrack = track
                        recentRepository.recordPlayed(track)
                    }

                    // Save the CURRENT track too so even the first song of a
                    // session is protected.
                    maybeAutoCacheTrack(track, autoCachedTrackIds)

                    // Pre-warm the server for the upcoming song (1-byte request:
                    // the server resolves + caches the real stream URL so the
                    // next play() skips the multi-second extraction).
                    val nextTrack = state.playlist.getOrNull(state.currentTrackIndex + 1)
                    if (nextTrack != null && nextTrack.id != lastWarmUpTrackId) {
                        warmUpStream(nextTrack)
                    }
                }
            }
        }
    }

    private fun maybeAutoCacheTrack(
        track: Track,
        evaluatedTrackIds: MutableSet<String>
    ) {
        if (track.id in evaluatedTrackIds) return
        if (!autoCacheEnabled.value) return
        // Only streamed tracks can be auto-cached; local files are already offline.
        if (!track.mediaUri.startsWith("http")) return
        if (!isNetworkAvailable()) return

        if (downloadManager.isDownloading(track.id)) return
        if (downloads.value.any { it.trackId == track.id && it.isCompleted() }) return

        evaluatedTrackIds.add(track.id)
        downloadManager.startDownload(track, autoCached = true)
    }

    private fun isNetworkAvailable(): Boolean {
        return try {
            val connectivityManager = appContext
                .getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
            val network = connectivityManager.activeNetwork ?: return false
            val capabilities = connectivityManager.getNetworkCapabilities(network) ?: return false
            capabilities.hasCapability(android.net.NetworkCapabilities.NET_CAPABILITY_INTERNET)
        } catch (_: Exception) {
            true
        }
    }

    private fun warmUpStream(nextTrack: Track) {
        if (!nextTrack.mediaUri.startsWith("http")) return
        if (!isNetworkAvailable()) {
            lastWarmUpTrackId = nextTrack.id
            return
        }
        lastWarmUpTrackId = nextTrack.id
        scope.launch(Dispatchers.IO) {
            try {
                val request = Request.Builder()
                    .url(nextTrack.mediaUri)
                    .header("Range", "bytes=0-0")
                    .build()
                warmUpClient.newCall(request).execute().use { response ->
                    response.body?.close()
                }
            } catch (_: Exception) {
                // Warm-up is best-effort; playback retries normally anyway.
            }
        }
    }
}
