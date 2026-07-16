import type { CapacitorConfig } from "@capacitor/cli";

// App nativo (Android/iOS) do AFJ CORE via Capacitor. A casca nativa carrega
// o PWA endurecido (Fases 45–47) diretamente da produção via `server.url` —
// assim o app fica sempre atualizado sem republicar na loja a cada deploy.
// Defina CAPACITOR_SERVER_URL com o domínio de produção do escritório.
const config: CapacitorConfig = {
  appId: "br.com.afjadvogados.core",
  appName: "AFJ CORE",
  // Shell local (splash/offline) usado antes de o app remoto carregar.
  webDir: "capacitor-shell",
  server: {
    url: process.env.CAPACITOR_SERVER_URL || "https://afj-core.vercel.app",
    cleartext: false,
  },
  backgroundColor: "#1E2229",
  android: {
    backgroundColor: "#1E2229",
  },
  ios: {
    backgroundColor: "#1E2229",
    contentInset: "always",
  },
};

export default config;
