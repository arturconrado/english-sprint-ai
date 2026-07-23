package com.arturconrado.englishsprint.voice

internal class SessionGenerationGate {
    private var current = 0

    fun next(): Int {
        current += 1
        return current
    }

    fun invalidate() {
        current += 1
    }

    fun accepts(generation: Int): Boolean = generation == current
}
