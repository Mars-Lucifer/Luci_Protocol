package com.example.luci_protocol

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.foundation.layout.Column
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.sp
import androidx.activity.SystemBarStyle
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.example.luci_protocol.R
import com.example.luci_protocol.ui.theme.luciColors
import kotlinx.coroutines.delay

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge(statusBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT))
        setContent {
            Scaffold(
                modifier = Modifier.fillMaxSize(),
                containerColor = luciColors.Black,
                content = {padding: PaddingValues ->
                    Column(
                        modifier = Modifier
                            .padding(padding)
                            .padding(horizontal = 40.dp)
                            .padding(bottom = 40.dp)
                            .fillMaxSize(),
                        verticalArrangement = Arrangement.SpaceBetween
                    ) {
                        HeaderBlock("Luci Protocol") {
                            DataBlock()
                        }
                        bottomMenu()
                    }
                }
            )
        }
    }
}

@Composable
fun HeaderBlock(text: String, content: @Composable () -> Unit = {}) {
    Column(
        modifier = Modifier
            .padding(top = 40.dp)
            .fillMaxWidth(),
        horizontalAlignment = Alignment.Start,
        verticalArrangement = Arrangement.spacedBy(40.dp)
    ) {
        Text(
            text=text,
            fontSize = 36.sp,
            fontWeight = FontWeight.SemiBold,
            color = luciColors.White
        )

        content()
    }
}

@Composable
fun DataBlock() {
    var downloadProgress by remember { mutableStateOf(0) }
    var uploadProgress by remember { mutableStateOf(0) }
    var msRand by remember { mutableStateOf(0) }

    LaunchedEffect(Unit) {
        while (true) {
            delay(500)
            downloadProgress = (0..16).random()
            uploadProgress = (0..16).random()
            msRand = downloadProgress * uploadProgress
        }
    }

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .border(width = 1.dp, color = luciColors.Stoke, shape = RoundedCornerShape(22.dp))
            .padding(22.dp),
        verticalArrangement = Arrangement.spacedBy(22.dp),

    ) {
        Text(
            text="Данные подключения",
            fontSize = 24.sp,
            fontWeight = FontWeight.SemiBold,
            color = luciColors.White
        )

        // Загрузка
        SegmentedProgressBar(col = downloadProgress, activeColor = luciColors.Red, text = "Загрузка")

        // Выгрузка
        SegmentedProgressBar(col = uploadProgress, activeColor = luciColors.Green, text = "Выгрузка")

        // Ping
        Blank(msRand.toString())
    }
}

@Composable
fun SegmentedProgressBar(col: Int, activeColor: Color, text: String) {
    Column(
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            for (i in 0 until 20) {
                val colorSet = if (i < col) activeColor else luciColors.Gray

                val animatedColor by animateColorAsState(
                    targetValue = colorSet,
                    animationSpec = tween(durationMillis = 150) // Длительность анимации
                )

                Box(
                    modifier = Modifier
                        .weight(1f)
                        .height(26.dp)
                        .background(animatedColor)
                )
            }
        }
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Text(
                text = "6 мб/c",
                fontSize = 16.sp,
                fontWeight = FontWeight.SemiBold,
                color = activeColor
            )
            Text(
                text = text,
                fontSize = 16.sp,
                fontWeight = FontWeight.SemiBold,
                color = luciColors.White
            )
        }
    }
}

@Composable
fun Blank(ms: String) {
    Row(modifier = Modifier
        .background(luciColors.GrayMinus, shape = RoundedCornerShape(18.dp))
        .padding(14.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        Text(
            text = "Пинг",
            fontSize = 16.sp,
            fontWeight = FontWeight.SemiBold,
            color = luciColors.White
        )
        Text(
            text = ms + "ms",
            fontSize = 16.sp,
            fontWeight = FontWeight.SemiBold,
            color = luciColors.Green
        )
    }
}

@Composable
fun bottomMenu() {
    Row(
        horizontalArrangement = Arrangement.spacedBy(4.dp),
        modifier = Modifier.fillMaxWidth()
    ) {
        Button(
            onClick = {},
            shape = RoundedCornerShape(22.dp),
            colors = ButtonDefaults.buttonColors(containerColor = luciColors.GrayMinus),
            contentPadding = PaddingValues(22.dp)
        ) {
            Icon(
                painter = painterResource(id = R.drawable.settings),
                contentDescription = "Settings",
                modifier = Modifier.size(28.dp),
                tint = Color.Unspecified
            )
        }
        Button(
            onClick = {},
            shape = RoundedCornerShape(22.dp),
            colors = ButtonDefaults.buttonColors(containerColor = luciColors.Red),
            contentPadding = PaddingValues(22.dp),
            modifier = Modifier.fillMaxWidth()
        ) {
            Text(
                text = "Подключиться",
                fontWeight = FontWeight.SemiBold,
                fontSize = 20.sp,
                color = luciColors.White
            )
        }
    }
}