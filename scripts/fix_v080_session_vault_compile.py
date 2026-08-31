from pathlib import Path

path = Path('app/src/main/java/com/admissionhub/collector/session/SecureSessionVault.kt')
text = path.read_text()
old = '''    private fun safeOrigin(raw: String): String? = try {
        val uri = URI(raw)
        val scheme = uri.scheme?.lowercase()?.takeIf { it == "https" } ?: return null
        val host = uri.host?.lowercase()?.takeIf { it.isNotBlank() } ?: return null
        "$scheme://$host/"
    } catch (_: Exception) { null }
'''
new = '''    private fun safeOrigin(raw: String): String? {
        return try {
            val uri = URI(raw)
            val scheme = uri.scheme?.lowercase()?.takeIf { it == "https" } ?: return null
            val host = uri.host?.lowercase()?.takeIf { it.isNotBlank() } ?: return null
            "$scheme://$host/"
        } catch (_: Exception) {
            null
        }
    }
'''
if text.count(old) != 1:
    raise SystemExit(f'safeOrigin compile anchor count={text.count(old)}')
path.write_text(text.replace(old, new, 1))
print('v0.8.0 SecureSessionVault safeOrigin compile fix applied')
