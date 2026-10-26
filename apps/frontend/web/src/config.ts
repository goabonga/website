/**
 * Configuration loader from injected window.APP_CONFIG.
 */

export interface LegalConfig {
  companyName: string;
  address: string;
  city: string;
  country: string;
  directorName: string;
  hostName: string;
  hostAddress: string;
  hostCity: string;
  hostCountry: string;
  hostPhone: string;
  hostWebsite: string;
}

export interface AppConfig {
  appName: string;
  authUrl: string;
  apiUrl: string;
  analyticsUrl: string;
  clientId: string;
  welcomeName: string;
  welcomeWords: string[];
  legal: LegalConfig;
}

const defaultConfig: AppConfig = {
  appName: 'GOABONGA',
  authUrl: '',
  apiUrl: '',
  analyticsUrl: '',
  clientId: '',
  welcomeName: 'Chris',
  welcomeWords: ['super', 'cool', 'awesome', 'great'],
  legal: {
    companyName: 'GOABONGA',
    address: '',
    city: '',
    country: '',
    directorName: '',
    hostName: '',
    hostAddress: '',
    hostCity: '',
    hostCountry: '',
    hostPhone: '',
    hostWebsite: '',
  },
};

/**
 * Get application configuration from window.APP_CONFIG.
 * Falls back to default values in development mode.
 */
export function getConfig(): AppConfig {
  const windowConfig = (window as Window & { APP_CONFIG?: Partial<AppConfig> })
    .APP_CONFIG;

  if (!windowConfig) {
    console.warn('APP_CONFIG not found, using defaults');
    return defaultConfig;
  }

  return {
    ...defaultConfig,
    ...windowConfig,
    legal: {
      ...defaultConfig.legal,
      ...(windowConfig.legal || {}),
    },
  };
}

export const config = getConfig();
