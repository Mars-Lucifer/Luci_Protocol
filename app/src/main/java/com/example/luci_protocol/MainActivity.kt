package com.example.luci_protocol

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.net.VpnService
import android.os.Bundle
import android.util.Log
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
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.Placeholder
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.app.ActivityCompat.startActivityForResult
import androidx.navigation.NavController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.example.luci_protocol.R
import com.example.luci_protocol.ui.theme.luciColors
import kotlinx.coroutines.delay

class MainActivity : ComponentActivity() {

    private var onVpnPermissionGranted: (() -> Unit)? = null

    private val vpnPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            if (result.resultCode == Activity.RESULT_OK) {
                onVpnPermissionGranted?.invoke()
            }
            onVpnPermissionGranted = null
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge(statusBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT))

        setContent {
            val navController = rememberNavController()
            var vpnRunning by remember { mutableStateOf(false) }

            NavHost(
                navController = navController,
                startDestination = "main"
            ) {
                composable("main") {
                    MainScreen(
                        navController = navController,
                        state = "main",
                        vpnEnabled = vpnRunning,
                        startVpnAction = {
                            startVpn(
                                onStarted = { vpnRunning = true },
                                onPermissionNeeded = { launch ->
                                    onVpnPermissionGranted = launch
                                }
                            )
                        },
                        stopVpnAction = {
                            stopVpn()
                            vpnRunning = false
                        }
                    )
                }

                composable("settings") {
                    SettingsScreen(
                        navController = navController,
                        state = "settings",
                        onCheck = { }
                    )
                }
            }
        }
    }

    private fun startVpn(
        onStarted: () -> Unit,
        onPermissionNeeded: ((() -> Unit) -> Unit)
    ) {
        val intent = VpnService.prepare(this)
        if (intent != null) {
            onPermissionNeeded {
                startService(Intent(this, MyVpnService::class.java))
                onStarted()
            }
            vpnPermissionLauncher.launch(intent)
        } else {
            startService(Intent(this, MyVpnService::class.java))
            onStarted()
        }
    }

    private fun stopVpn() {
        val intent = Intent(this, MyVpnService::class.java)
        stopService(intent)
    }
}


@Composable
fun MainScreen(
    navController: NavController,
    state: String,
    vpnEnabled: Boolean,
    startVpnAction: () -> Unit,
    stopVpnAction: () -> Unit
) {
    Scaffold(
        modifier = Modifier.fillMaxSize(),
        containerColor = luciColors.Black,
        content = { padding: PaddingValues ->
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
                BottomMenu(
                    navController = navController,
                    state = state,
                    vpnEnabled = vpnEnabled,
                    startVpnAction = startVpnAction,
                    stopVpnAction = stopVpnAction,
                    onCheck = { }
                )
            }
        }
    )
}

@Composable
fun SettingsScreen(
    navController: NavController,
    state: String,
    onCheck: () -> Unit
) {
    Scaffold(
        modifier = Modifier.fillMaxSize(),
        containerColor = luciColors.Black,
        content = { padding: PaddingValues ->
            Column(
                modifier = Modifier
                    .padding(padding)
                    .padding(horizontal = 40.dp)
                    .padding(bottom = 40.dp)
                    .fillMaxSize(),
                verticalArrangement = Arrangement.SpaceBetween
            ) {
                HeaderBlock("Настройки") {
                    SettingsBlock()
                }
                BottomMenu(
                    navController = navController,
                    state = state,
                    vpnEnabled = false,
                    startVpnAction = {},
                    stopVpnAction = {},
                    onCheck = onCheck
                )
            }
        }
    )
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
fun BottomMenu(
    navController: NavController,
    state: String,
    vpnEnabled: Boolean,
    startVpnAction: () -> Unit,
    stopVpnAction: () -> Unit,
    onCheck: () -> Unit
) {
    Row(
        horizontalArrangement = Arrangement.spacedBy(4.dp),
        modifier = Modifier.fillMaxWidth()
    ) {

        // 1. Settings / Back
        Button(
            onClick = {
                if (state == "main") {
                    navController.navigate("settings")
                } else {
                    navController.popBackStack()
                }
            },
            shape = RoundedCornerShape(22.dp),
            colors = ButtonDefaults.buttonColors(containerColor = luciColors.GrayMinus),
            contentPadding = PaddingValues(22.dp)
        ) {
            Icon(
                painter = painterResource(
                    id = if (state == "main")
                        R.drawable.settings
                    else
                        R.drawable.back
                ),
                contentDescription = null,
                modifier = Modifier.size(28.dp),
                tint = Color.Unspecified
            )
        }

        // 2. Главная кнопка (меняется по state)
        Button(
            onClick = {
                if (state == "main") {
                    if (!vpnEnabled) startVpnAction() else stopVpnAction()
                } else {
                    onCheck()
                }
            },
            shape = RoundedCornerShape(22.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = when {
                    state == "settings" -> luciColors.GrayMinus
                    vpnEnabled -> luciColors.GrayMinus
                    else -> luciColors.Red
                }
            ),
            contentPadding = PaddingValues(22.dp),
            modifier = Modifier.fillMaxWidth()
        ) {
            Text(
                text = when (state) {
                    "main" ->
                        if (!vpnEnabled) "Подключиться" else "Отключиться"

                    "settings" ->
                        "Проверить"

                    else -> ""
                },
                fontWeight = FontWeight.SemiBold,
                fontSize = 18.sp,
                color = luciColors.White
            )
        }
    }
}

@Composable
fun SettingsBlock() {
    var token by remember { mutableStateOf("") }
    var server by remember { mutableStateOf("") }
    Column(
        verticalArrangement = Arrangement.spacedBy(8.dp),
        modifier = Modifier.fillMaxWidth()
    ) {
        Text(
            fontSize = 24.sp,
            fontWeight = FontWeight.SemiBold,
            color = luciColors.White,
            text="__oneme_auth"
        )
        TextField(

            modifier = Modifier
                .fillMaxWidth()
                .padding(18.dp)
                .border(width = 1.dp, color = luciColors.Stoke, shape = RoundedCornerShape(18.dp))
            ,
            textStyle = TextStyle(
                color = luciColors.White,
                fontWeight = FontWeight.SemiBold,
                fontSize = 16.sp
            ),
            colors = TextFieldDefaults.colors(
                focusedTextColor = luciColors.White,
                unfocusedTextColor = luciColors.White,

                focusedPlaceholderColor = luciColors.GrayText,
                unfocusedPlaceholderColor = luciColors.GrayText,

                focusedContainerColor = Color.Transparent,
                unfocusedContainerColor = Color.Transparent,
                disabledContainerColor = Color.Transparent,

                focusedIndicatorColor = Color.Transparent,
                unfocusedIndicatorColor = Color.Transparent,
                disabledIndicatorColor = Color.Transparent
            ),
            value = token,
            onValueChange = { token = it },
            placeholder = {Text("{token: “abc...”, viewerId: 123456}")}
        )
    }
    Column(
        verticalArrangement = Arrangement.spacedBy(8.dp),
        modifier = Modifier.fillMaxWidth()
    ) {
        Text(
            fontSize = 24.sp,
            fontWeight = FontWeight.SemiBold,
            color = luciColors.White,
            text="Сервер"
        )
        TextField(
            modifier = Modifier
                .fillMaxWidth()
                .padding(18.dp)
                .border(width = 1.dp, color = luciColors.Stoke, shape = RoundedCornerShape(18.dp))
            ,
            textStyle = TextStyle(
                color = luciColors.White,
                fontWeight = FontWeight.SemiBold,
                fontSize = 16.sp
            ),
            colors = TextFieldDefaults.colors(
                focusedTextColor = luciColors.White,
                unfocusedTextColor = luciColors.White,

                focusedPlaceholderColor = luciColors.GrayText,
                unfocusedPlaceholderColor = luciColors.GrayText,

                focusedContainerColor = Color.Transparent,
                unfocusedContainerColor = Color.Transparent,
                disabledContainerColor = Color.Transparent,

                focusedIndicatorColor = Color.Transparent,
                unfocusedIndicatorColor = Color.Transparent,
                disabledIndicatorColor = Color.Transparent
            ),
            value = server,
            onValueChange = { server = it },
            placeholder = {Text("Введите IP/домен сервера")},
        )
    }
}