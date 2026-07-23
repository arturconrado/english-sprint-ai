package com.arturconrado.englishsprint

import platform.UIKit.UIDevice

actual fun platformName(): String = buildString {
    append(UIDevice.currentDevice.systemName)
    append(" ")
    append(UIDevice.currentDevice.systemVersion)
}
