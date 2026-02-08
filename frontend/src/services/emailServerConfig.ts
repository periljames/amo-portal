export type EmailProvider =
  | "none"
  | "smtp"
  | "sendgrid"
  | "ses"
  | "mailgun"
  | "postmark"
  | "custom_http";

export type AuthScheme = "none" | "bearer" | "basic" | "header";

export type EmailServerConfig = {
  provider: EmailProvider;
  label: string;
  fromName: string;
  fromEmail: string;
  replyTo: string;
  sandboxMode: boolean;
  testEndpointUrl: string;
  testTimeoutMs: number;
  smtp: {
    host: string;
    port: number;
    username: string;
    password: string;
    secure: boolean;
    allowSelfSigned: boolean;
    connectionTimeoutMs: number;
  };
  sendgrid: {
    apiKey: string;
    subaccount: string;
    ipPool: string;
  };
  ses: {
    accessKeyId: string;
    secretAccessKey: string;
    region: string;
    configurationSet: string;
  };
  mailgun: {
    apiKey: string;
    domain: string;
    region: "us" | "eu";
  };
  postmark: {
    serverToken: string;
    messageStream: string;
  };
  customHttp: {
    baseUrl: string;
    authScheme: AuthScheme;
    authToken: string;
    username: string;
    password: string;
    headerName: string;
    headerValue: string;
    timeoutMs: number;
  };
};

const STORAGE_KEY = "amo_email_server_config";

export const defaultEmailServerConfig: EmailServerConfig = {
  provider: "none",
  label: "Primary outbound email",
  fromName: "AMO Portal",
  fromEmail: "",
  replyTo: "",
  sandboxMode: false,
  testEndpointUrl: "",
  testTimeoutMs: 8000,
  smtp: {
    host: "",
    port: 587,
    username: "",
    password: "",
    secure: true,
    allowSelfSigned: false,
    connectionTimeoutMs: 10000,
  },
  sendgrid: {
    apiKey: "",
    subaccount: "",
    ipPool: "",
  },
  ses: {
    accessKeyId: "",
    secretAccessKey: "",
    region: "us-east-1",
    configurationSet: "",
  },
  mailgun: {
    apiKey: "",
    domain: "",
    region: "us",
  },
  postmark: {
    serverToken: "",
    messageStream: "outbound",
  },
  customHttp: {
    baseUrl: "",
    authScheme: "none",
    authToken: "",
    username: "",
    password: "",
    headerName: "",
    headerValue: "",
    timeoutMs: 8000,
  },
};

export function loadEmailServerConfig(): EmailServerConfig {
  if (typeof window === "undefined") {
    return defaultEmailServerConfig;
  }
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) return defaultEmailServerConfig;
  try {
    const parsed = JSON.parse(raw) as EmailServerConfig;
    return {
      ...defaultEmailServerConfig,
      ...parsed,
      smtp: { ...defaultEmailServerConfig.smtp, ...parsed.smtp },
      sendgrid: { ...defaultEmailServerConfig.sendgrid, ...parsed.sendgrid },
      ses: { ...defaultEmailServerConfig.ses, ...parsed.ses },
      mailgun: { ...defaultEmailServerConfig.mailgun, ...parsed.mailgun },
      postmark: { ...defaultEmailServerConfig.postmark, ...parsed.postmark },
      customHttp: { ...defaultEmailServerConfig.customHttp, ...parsed.customHttp },
    };
  } catch {
    return defaultEmailServerConfig;
  }
}

export function saveEmailServerConfig(config: EmailServerConfig): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
}

export function clearEmailServerConfig(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
}
