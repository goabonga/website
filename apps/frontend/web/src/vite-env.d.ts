/// <reference types="vite/client" />

interface AppConfig {
  appName: string;
  authUrl: string;
  apiUrl: string;
  clientId: string;
}

interface Window {
  APP_CONFIG?: Partial<AppConfig>;
}
