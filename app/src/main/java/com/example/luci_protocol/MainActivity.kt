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
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.Alignment
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.example.luci_protocol.ui.theme.luciColors

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
                            .fillMaxSize()
                    ) {
                        HeaderBlock("Luci Protocol") {
                            DataBlock()
                        }
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
        Column(
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            SegmentedProgressBar()
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(
                    text="3 мб/c",
                    fontSize = 16.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = luciColors.Red
                )
                Text(
                    text="Загрузка",
                    fontSize = 16.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = luciColors.White
                )
            }
        }
    }
}

@Composable
fun SegmentedProgressBar() {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(6.dp)
    ) {
        for (i in 0 until 16) {
            Box(
                modifier = Modifier
                    .weight(1f)
                    .height(26.dp)
                    .background(luciColors.Gray)
            )
        }
    }
}