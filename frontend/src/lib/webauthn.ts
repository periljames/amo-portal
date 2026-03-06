const b64ToBytes = (value: string): ArrayBuffer => {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
  const decoded = atob(padded);
  const bytes = Uint8Array.from(decoded, (c) => c.charCodeAt(0));
  return bytes.buffer;
};

const bytesToB64Url = (bytes: ArrayBuffer): string => {
  const raw = String.fromCharCode(...new Uint8Array(bytes));
  return btoa(raw).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
};

export const isWebAuthnSupported = () =>
  typeof window !== "undefined" &&
  typeof window.PublicKeyCredential !== "undefined" &&
  typeof navigator !== "undefined" &&
  !!navigator.credentials;

export const isSecureContextAvailable = () => typeof window !== "undefined" && !!window.isSecureContext;

export const decodeCreationOptions = (options: Record<string, unknown>): PublicKeyCredentialCreationOptions => {
  const parsed = options as {
    challenge: string;
    user: { id: string; name: string; displayName: string };
    excludeCredentials?: Array<{ id: string; type: PublicKeyCredentialType; transports?: AuthenticatorTransport[] }>;
  } & Record<string, unknown>;

  return {
    ...(parsed as unknown as PublicKeyCredentialCreationOptions),
    challenge: b64ToBytes(parsed.challenge),
    user: {
      ...(parsed.user as unknown as PublicKeyCredentialUserEntity),
      id: b64ToBytes(parsed.user.id),
    },
    excludeCredentials: (parsed.excludeCredentials || []).map((cred) => ({
      ...cred,
      id: b64ToBytes(cred.id),
    })),
  };
};

export const decodeRequestOptions = (options: Record<string, unknown>): PublicKeyCredentialRequestOptions => {
  const parsed = options as {
    challenge: string;
    allowCredentials?: Array<{ id: string; type: PublicKeyCredentialType; transports?: AuthenticatorTransport[] }>;
  } & Record<string, unknown>;

  return {
    ...(parsed as unknown as PublicKeyCredentialRequestOptions),
    challenge: b64ToBytes(parsed.challenge),
    allowCredentials: (parsed.allowCredentials || []).map((cred) => ({
      ...cred,
      id: b64ToBytes(cred.id),
    })),
  };
};

export const createCredential = async (options: PublicKeyCredentialCreationOptions): Promise<PublicKeyCredential | null> => {
  const credential = (await navigator.credentials.create({ publicKey: options })) as PublicKeyCredential | null;
  return credential;
};

export const getAssertion = async (options: PublicKeyCredentialRequestOptions): Promise<PublicKeyCredential | null> => {
  const credential = (await navigator.credentials.get({ publicKey: options })) as PublicKeyCredential | null;
  return credential;
};

export const serializeRegistrationCredential = (credential: PublicKeyCredential) => {
  const response = credential.response as AuthenticatorAttestationResponse;
  return {
    id: credential.id,
    rawId: bytesToB64Url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: bytesToB64Url(response.clientDataJSON),
      attestationObject: bytesToB64Url(response.attestationObject),
      transports: typeof response.getTransports === "function" ? response.getTransports() : undefined,
    },
  };
};

export const serializeAssertionCredential = (credential: PublicKeyCredential) => {
  const response = credential.response as AuthenticatorAssertionResponse;
  return {
    id: credential.id,
    rawId: bytesToB64Url(credential.rawId),
    type: credential.type,
    response: {
      authenticatorData: bytesToB64Url(response.authenticatorData),
      clientDataJSON: bytesToB64Url(response.clientDataJSON),
      signature: bytesToB64Url(response.signature),
      userHandle: response.userHandle ? bytesToB64Url(response.userHandle) : null,
    },
  };
};
