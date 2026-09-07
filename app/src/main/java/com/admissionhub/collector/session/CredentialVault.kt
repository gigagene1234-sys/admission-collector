package com.admissionhub.collector.session

import android.content.Context

/** Removes the old custom credential copy; existing SQLite and native WebView sessions are untouched. */
class CredentialVault(context: Context) {
    private val legacy = context.applicationContext.getSharedPreferences("admission_local_credentials_v1", Context.MODE_PRIVATE)
    init { legacy.edit().clear().commit() }
    fun has(provider: String): Boolean = false
    fun clear(provider: String) { legacy.edit().remove("credential_${provider.lowercase()}").commit() }
}
