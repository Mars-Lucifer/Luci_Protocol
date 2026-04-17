package com.example.luci_protocol.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import androidx.compose.ui.text.font.Font
import com.example.luci_protocol.R

val Manrope = FontFamily(
    Font(resId = R.font.manrope_extralight, weight = FontWeight.ExtraLight),
    Font(resId = R.font.manrope_light, weight = FontWeight.Light),
    Font(resId = R.font.manrope_regular, weight = FontWeight.Normal),
    Font(resId = R.font.manrope_medium, weight = FontWeight.Medium),
    Font(resId = R.font.manrope_bold, weight = FontWeight.Bold),
    Font(resId = R.font.manrope_semibold, weight = FontWeight.SemiBold),
    Font(resId = R.font.manrope_extrabold, weight = FontWeight.ExtraBold)
)

// Set of Material typography styles to start with
val Typography = Typography(
    bodyLarge = TextStyle(
        fontFamily = Manrope,
        fontWeight = FontWeight.Normal,
        fontSize = 20.sp,
        lineHeight = 24.sp,
        letterSpacing = 0.5.sp
    )
)