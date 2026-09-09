from pathlib import Path

BASE = Path(__file__).with_name("patch_v0174_harden.py").resolve()
namespace = {"__name__": "__main__", "__file__": str(BASE)}
exec(compile(BASE.read_text(), str(BASE), "exec"), namespace, namespace)

root = Path(__file__).resolve().parents[2]
main_path = root / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
text = main_path.read_text()
remaining = text.count("webView.loadUrl(retryOrigin)")
if remaining:
    text = text.replace(
        "webView.loadUrl(retryOrigin)",
        'loadJinhakV0174High3Only(retryOrigin, "remaining-retry-origin")'
    )
main_path.write_text(text)
print(f"v0.17.4 hardening retry removed {remaining} remaining direct retryOrigin load(s)")
