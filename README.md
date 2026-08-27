# Admission Collector v0.1

Android companion app for the 08 PROJECT Admission Hub.

## v0.1

- Opens official 어디가 and 진학사 sites in an Android WebView.
- Login/CAPTCHA/Turnstile/additional verification is performed manually by the user.
- `현재 페이지 수집` collects only visible admission-result text from the current page.
- It deliberately removes form controls, scripts, hidden fields, and authentication-related elements from collection.
- It does not read or export cookies, session tokens, LocalStorage, SessionStorage, passwords, CAPTCHA, CSRF, TransKey, or authentication headers.
- Preview is shown in-app and can be saved as JSON through Android's system document picker.

## Build

GitHub Actions workflow: `.github/workflows/android.yml`

On push to `main` (or manual dispatch), it builds:

`app/build/outputs/apk/debug/app-debug.apk`

and uploads artifact:

`admission-collector-debug`

## Validation order

1. Install APK on the user's Galaxy Tab.
2. Test 어디가 manual login and a real admission result page.
3. Tap `현재 페이지 수집` and compare preview with visible data.
4. Revise parser using the real DOM.
5. Repeat on 진학사.
6. Add Hub/Cloud DB sync only after real-page parser validation.
