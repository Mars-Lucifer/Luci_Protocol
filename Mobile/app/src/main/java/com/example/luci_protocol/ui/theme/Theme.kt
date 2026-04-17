package com.example.luci_protocol.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// Твоя единственная палитра
private val DarkColorScheme = darkColorScheme(
    primary = Color.White,        // Акценты (текст кнопок и т.д.) будут белыми
)

@Composable
fun Luci_ProtocolTheme(
    content: @Composable () -> Unit
) {
    // Мы игнорим системные настройки и всегда передаем DarkColorScheme
    MaterialTheme(
        colorScheme = DarkColorScheme,
        typography = Typography,
        content = content
    )
}