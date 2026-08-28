package com.admissionhub.collector

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.os.IBinder

/**
 * Keeps the collector process at foreground-service priority while a batch crawl is active.
 *
 * The actual browser remains in-process so WebView cookies are never exported to Cloudflare.
 * If Android or the user force-stops the process, the next app launch resumes from the
 * Cloudflare checkpoint instead of pretending the browser can survive process death.
 */
class CollectionKeepAliveService : Service() {
    override fun onCreate() {
        super.onCreate()
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(
                CHANNEL_ID,
                "Admission Collector background collection",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Keeps an active admission-data collection session running in the background."
            }
        )
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val notification = android.app.Notification.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_sys_download)
            .setContentTitle("Admission Collector 수집 중")
            .setContentText("백그라운드 수집을 유지하고 있습니다. 로그인 만료 시 앱에서 갱신하세요.")
            .setOngoing(true)
            .setCategory(android.app.Notification.CATEGORY_PROGRESS)
            .build()
        startForeground(NOTIFICATION_ID, notification)
        return START_NOT_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    companion object {
        private const val CHANNEL_ID = "admission_collection"
        private const val NOTIFICATION_ID = 32033
    }
}
