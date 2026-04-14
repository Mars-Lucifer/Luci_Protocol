package com.example.luci_protocol

import android.content.Intent
import android.net.VpnService
import android.os.ParcelFileDescriptor
import android.util.Log
import java.io.FileInputStream
import java.io.IOException
import java.util.concurrent.atomic.AtomicBoolean

class MyVpnService : VpnService(), Runnable {

    private var thread: Thread? = null
    private var vpnInterface: ParcelFileDescriptor? = null
    private var input: FileInputStream? = null
    private val running = AtomicBoolean(false)

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Log.e("VPN", "onStartCommand")
        if (thread != null) return START_NOT_STICKY

        running.set(true)
        thread = Thread(this, "MyVpnThread").also { it.start() }
        return START_NOT_STICKY
    }

    override fun run() {
        try {
            val builder = Builder()
                .setSession("VPN")
                .addAddress("10.0.0.2", 24)
                .addRoute("0.0.0.0", 0)

            vpnInterface = builder.establish()
            if (vpnInterface == null) {
                Log.e("VPN", "establish() returned null")
                stopSelf()
                return
            }

            input = FileInputStream(vpnInterface!!.fileDescriptor)
            val buffer = ByteArray(32767)

            while (running.get()) {
                val len = try {
                    input?.read(buffer) ?: -1
                } catch (e: IOException) {
                    Log.e("VPN", "read() interrupted: ${e.message}")
                    break
                }

                if (len > 0) {
                    Log.d("VPN", "Packet size: $len")
                } else if (len < 0) {
                    break
                }
            }
        } catch (e: Exception) {
            Log.e("VPN", "Unexpected error: ${e.message}", e)
        } finally {
            releaseResources()
        }
    }

    override fun onDestroy() {
        Log.e("VPN", "onDestroy")
        stopVpnInternal()
        super.onDestroy()
    }

    fun stopVpn() {
        Log.e("VPN", "stopVpn() called")
        stopVpnInternal()
        stopSelf()
    }

    private fun stopVpnInternal() {
        running.set(false)
        try { input?.close() } catch (_: Exception) {}
        try { vpnInterface?.close() } catch (_: Exception) {}
        thread?.interrupt()
        thread = null
    }

    private fun releaseResources() {
        try { input?.close() } catch (_: Exception) {}
        try { vpnInterface?.close() } catch (_: Exception) {}
        input = null
        vpnInterface = null
    }
}