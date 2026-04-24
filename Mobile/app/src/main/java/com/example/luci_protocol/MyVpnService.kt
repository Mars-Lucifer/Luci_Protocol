package com.example.luci_protocol

import android.content.Context
import android.content.Intent
import android.net.VpnService
import android.os.ParcelFileDescriptor
import android.util.Log
import java.io.FileInputStream
import java.io.FileOutputStream
import java.nio.ByteBuffer

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
        val prefs = getSharedPreferences("vpn_settings", Context.MODE_PRIVATE)
        val token = prefs.getString("max_token", "") ?: ""
        val serverAddress = prefs.getString("server_address", "") ?: ""

        if (token.isEmpty() || serverAddress.isEmpty()) {
            Log.e("MyVpnService", "Настройки не заполнены: token или адрес сервера отсутствуют")
            stopSelf()
            return
        }

        try {
            val builder = Builder()
                .addAddress("10.0.0.2", 24)
                .addRoute("0.0.0.0", 0)
                .addDnsServer("8.8.8.8")
                .setSession("LuciProtocol")
                .setMtu(1500)

            vpnInterface = builder.establish()
            if (vpnInterface == null) {
                Log.e("MyVpnService", "Не удалось создать VPN интерфейс")
                stopSelf()
                return
            }
            
            isRunning = true
            vpnThread = Thread({
                runVpnLoop(serverAddress, token)
            }, "LuciVpnThread")
            vpnThread?.start()

            Log.d("MyVpnService", "VPN запущен успешно")
        } catch (e: Exception) {
            Log.e("MyVpnService", "Ошибка при запуске VPN", e)
            stopVpn()
        }
    }

    private fun runVpnLoop(serverAddress: String, token: String) {
        val inputStream = FileInputStream(vpnInterface?.fileDescriptor)
        val outputStream = FileOutputStream(vpnInterface?.fileDescriptor)
        val packet = ByteBuffer.allocate(32767)

        try {
            // Здесь должна быть логика работы с сервером по Luci Protocol:
            // 1. HTTP запрос к $serverAddress/connect/max для получения session_id и ключей
            // 2. Установка WebSocket соединения
            // 3. Шифрование и инкапсуляция пакетов
            
            Log.d("MyVpnService", "Вход в основной цикл VPN. Сервер: $serverAddress")

            while (isRunning && !Thread.interrupted()) {
                val length = inputStream.read(packet.array())
                if (length > 0) {
                    // Пакет получен из ОС
                    // TODO: Отправить зашифрованный пакет через WebSocket
                    // Log.v("MyVpnService", "Packet from OS: $length bytes")
                    packet.clear()
                }
                
                // TODO: Читать из WebSocket и писать в outputStream
                
                Thread.sleep(10)
            }
        } catch (e: Exception) {
            Log.e("MyVpnService", "Критическая ошибка в цикле VPN", e)
        } finally {
            try {
                inputStream.close()
                outputStream.close()
            } catch (e: Exception) { /* ignore */ }
        }
    }

    private fun stopVpn() {
        isRunning = false
        vpnThread?.interrupt()
        try {
            vpnInterface?.close()
        } catch (e: Exception) {
            Log.e("MyVpnService", "Ошибка при закрытии TUN", e)
        }
        vpnInterface = null
        Log.d("MyVpnService", "VPN остановлен")
        stopSelf()
    }

    override fun onDestroy() {
        super.onDestroy()
        stopVpn()
    }
}
