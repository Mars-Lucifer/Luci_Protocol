package com.example.luci_protocol

import android.content.Intent
import android.net.VpnService
import android.os.ParcelFileDescriptor
import android.util.Log
import java.io.FileInputStream

class MyVpnService : VpnService() {
    private var vpnInterface: ParcelFileDescriptor? = null
    private var isRunning = false
    private var vpnThread: Thread? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == "STOP") {
            stopVpn()
            return START_NOT_STICKY
        }

        if (!isRunning) {
            startVpn()
        }
        return START_STICKY
    }

    private fun startVpn() {
        try {
            val builder = Builder()
                .addAddress("10.0.0.2", 24)
                .addRoute("0.0.0.0", 0) // Перехватываем весь IPv4 трафик
                .setSession("LuciProtocol")
                .setMtu(1500)

            vpnInterface = builder.establish()
            isRunning = true

            // Заглушка: поток для чтения трафика, чтобы сервис не закрывался
            vpnThread = Thread {
                try {
                    val inputStream = FileInputStream(vpnInterface?.fileDescriptor)
                    val packet = ByteArray(32767)
                    while (isRunning && !Thread.interrupted()) {
                        val length = inputStream.read(packet)
                        if (length > 0) {
                            // Здесь будет шифрование и отправка в WebSockets
                            // Log.d("MyVpnService", "Прочитан пакет размером: $length")
                        }
                    }
                } catch (e: Exception) {
                    Log.e("MyVpnService", "Ошибка потока VPN", e)
                }
            }
            vpnThread?.start()

        } catch (e: Exception) {
            Log.e("MyVpnService", "Не удалось запустить VPN", e)
            stopVpn()
        }
    }

    private fun stopVpn() {
        isRunning = false
        vpnThread?.interrupt()
        try {
            vpnInterface?.close()
        } catch (e: Exception) {
            Log.e("MyVpnService", "Ошибка при закрытии интерфейса", e)
        }
        vpnInterface = null
        stopSelf()
    }

    override fun onDestroy() {
        super.onDestroy()
        stopVpn()
    }
}