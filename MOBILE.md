# App Android/iOS — AFJ CORE (Capacitor)

O app nativo é uma **casca Capacitor** que carrega o PWA endurecido (Fases 45–47)
direto da produção (`server.url` em `frontend/capacitor.config.ts`). Vantagem:
o app fica **sempre atualizado** a cada deploy, sem republicar na loja.

> **Você precisa** de: Node 22+, e — para gerar/compilar os projetos nativos —
> **Android Studio** (Android) e **Xcode em um Mac** (iOS). A base já está no repo;
> os comandos `cap add`/build rodam na sua máquina (SDKs nativos não existem no CI).

## 1. Pré-requisitos (uma vez)
```bash
cd frontend
npm install                     # instala as deps (Capacitor já está no package.json)
export CAPACITOR_SERVER_URL="https://SEU-DOMINIO-DE-PRODUCAO"   # ex.: https://afj-core.vercel.app
```
As dependências já incluídas: `@capacitor/core`, `@capacitor/cli`,
`@capacitor/android`, `@capacitor/ios`, `@capacitor/push-notifications`.

## 2. Gerar os projetos nativos
```bash
cd frontend
npx cap add android        # cria frontend/android (projeto Android Studio)
npx cap add ios            # cria frontend/ios (projeto Xcode) — só em macOS
npx cap sync               # aplica config + plugins
```

## 3. Ícones e splash
Reaproveite o ícone maskable já gerado (`frontend/public/icons/icon-maskable-512.png`):
```bash
npm i -D @capacitor/assets
npx capacitor-assets generate --iconBackgroundColor '#1E2229' --splashBackgroundColor '#1E2229'
```

## 4. Rodar / compilar
- **Android**: `npx cap open android` → Run no Android Studio (ou `./gradlew assembleRelease` para o APK/AAB).
- **iOS**: `npx cap open ios` → Run/Archive no Xcode.

## 5. Push nativo (FCM/APNs) — opcional
O sistema já tem Web Push (VAPID), que funciona no PWA. Para push **nativo** no app:
1. Android: crie um projeto no Firebase, baixe `google-services.json` para `frontend/android/app/`.
2. iOS: habilite Push Notifications no Xcode + APNs key no Apple Developer.
3. No app web (roda dentro da casca), registre o token só no nativo:
   ```ts
   import { Capacitor } from "@capacitor/core";
   import { PushNotifications } from "@capacitor/push-notifications";
   if (Capacitor.isNativePlatform()) {
     await PushNotifications.requestPermissions();
     await PushNotifications.register();
     PushNotifications.addListener("registration", (t) => {
       // POST o token FCM/APNs para o backend associar ao usuário
       fetch("/api/v1/push/native-token", { method: "POST", body: JSON.stringify({ token: t.value }) });
     });
   }
   ```
   (Endpoint de token nativo é um follow-up backend — o Web Push atual já cobre o PWA.)

## 6. Publicar (contas suas)
- **Google Play**: conta de desenvolvedor (**US$25, taxa única**) → suba o `.aab`.
- **App Store**: **Apple Developer (US$99/ano)** → Archive no Xcode → App Store Connect.
- `appId`: `br.com.afjadvogados.core` (ajuste em `capacitor.config.ts` se quiser outro).

## Alternativa só-Android (mais rápida)
Se quiser apenas Android sem Capacitor, use **TWA/Bubblewrap** apontando ao PWA:
`npx @bubblewrap/cli init --manifest https://SEU-DOMINIO/manifest.json`.
