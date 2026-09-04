// Minimal Cognito Hosted UI client: Authorization Code + PKCE, implemented directly
// against the standard OAuth2/OIDC endpoints with WebCrypto (no auth SDK dependency).
// When the NEXT_PUBLIC_COGNITO_* variables are unset, isAuthConfigured() is false and
// every function below is inert -- the app behaves exactly like the backend's
// AUTH_MODE=disabled: no sign-in wall, no token attached to requests. This repository
// does not provision or run a live Cognito user pool; this client only knows how to
// talk to one if the environment names one.

export const SESSION_EXPIRED_EVENT = "kyl:session-expired";

interface CognitoConfig {
  domain: string;
  clientId: string;
  redirectUri: string;
  scope: string;
}

function readConfig(): CognitoConfig | null {
  const domain = process.env.NEXT_PUBLIC_COGNITO_DOMAIN;
  const clientId = process.env.NEXT_PUBLIC_COGNITO_APP_CLIENT_ID;
  const redirectUri = process.env.NEXT_PUBLIC_COGNITO_REDIRECT_URI;
  if (!domain || !clientId || !redirectUri) return null;
  return { domain: domain.replace(/\/$/, ""), clientId, redirectUri, scope: "openid email" };
}

export function isAuthConfigured(): boolean {
  return readConfig() !== null;
}

const STORAGE_KEYS = {
  accessToken: "know-your-lease.auth.access-token",
  idToken: "know-your-lease.auth.id-token",
  refreshToken: "know-your-lease.auth.refresh-token",
  expiresAt: "know-your-lease.auth.expires-at",
} as const;

const PKCE_VERIFIER_KEY = "know-your-lease.auth.pkce-verifier";
const EXPIRY_LEEWAY_MS = 30_000;

function base64UrlEncode(bytes: Uint8Array): string {
  let binary = "";
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function sha256(value: string): Promise<Uint8Array> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return new Uint8Array(digest);
}

function randomVerifier(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return base64UrlEncode(bytes);
}

interface TokenResponse {
  access_token: string;
  id_token: string;
  refresh_token?: string;
  expires_in: number;
}

interface StoredTokens {
  accessToken: string;
  idToken: string;
  refreshToken: string | null;
  expiresAt: number;
}

function storeTokens(tokens: TokenResponse, fallbackRefreshToken?: string | null): void {
  const expiresAt = Date.now() + tokens.expires_in * 1000;
  window.localStorage.setItem(STORAGE_KEYS.accessToken, tokens.access_token);
  window.localStorage.setItem(STORAGE_KEYS.idToken, tokens.id_token);
  window.localStorage.setItem(STORAGE_KEYS.expiresAt, String(expiresAt));
  const refreshToken = tokens.refresh_token ?? fallbackRefreshToken ?? null;
  if (refreshToken) window.localStorage.setItem(STORAGE_KEYS.refreshToken, refreshToken);
}

function readStoredTokens(): StoredTokens | null {
  if (typeof window === "undefined") return null;
  const accessToken = window.localStorage.getItem(STORAGE_KEYS.accessToken);
  const idToken = window.localStorage.getItem(STORAGE_KEYS.idToken);
  const expiresAtRaw = window.localStorage.getItem(STORAGE_KEYS.expiresAt);
  if (!accessToken || !idToken || !expiresAtRaw) return null;
  return {
    accessToken,
    idToken,
    refreshToken: window.localStorage.getItem(STORAGE_KEYS.refreshToken),
    expiresAt: Number(expiresAtRaw),
  };
}

export function clearSession(): void {
  if (typeof window === "undefined") return;
  for (const key of Object.values(STORAGE_KEYS)) window.localStorage.removeItem(key);
}

export function notifySessionExpired(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
}

async function requestTokens(
  config: CognitoConfig,
  body: URLSearchParams,
): Promise<TokenResponse | null> {
  let response: Response;
  try {
    response = await fetch(`${config.domain}/oauth2/token`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
  } catch {
    return null;
  }
  if (!response.ok) return null;
  return (await response.json()) as TokenResponse;
}

async function refreshAccessToken(
  config: CognitoConfig,
  refreshToken: string,
): Promise<StoredTokens | null> {
  const tokens = await requestTokens(
    config,
    new URLSearchParams({
      grant_type: "refresh_token",
      client_id: config.clientId,
      refresh_token: refreshToken,
    }),
  );
  if (!tokens) return null;
  storeTokens(tokens, refreshToken);
  return readStoredTokens();
}

/** Returns a valid access token, refreshing it first if it is expired or near expiry.
 * Returns null when Cognito is not configured (local/dev, matching AUTH_MODE=disabled)
 * or when there is no usable session. */
export async function getAccessToken(): Promise<string | null> {
  const config = readConfig();
  if (!config) return null;

  const stored = readStoredTokens();
  if (!stored) return null;
  if (Date.now() < stored.expiresAt - EXPIRY_LEEWAY_MS) return stored.accessToken;

  if (!stored.refreshToken) {
    clearSession();
    return null;
  }
  const refreshed = await refreshAccessToken(config, stored.refreshToken);
  if (!refreshed) {
    clearSession();
    return null;
  }
  return refreshed.accessToken;
}

export async function isSignedIn(): Promise<boolean> {
  if (!isAuthConfigured()) return true;
  return (await getAccessToken()) !== null;
}

function buildHostedUiUrl(
  config: CognitoConfig,
  path: string,
  params: Record<string, string>,
): URL {
  const url = new URL(`${config.domain}${path}`);
  url.searchParams.set("client_id", config.clientId);
  for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);
  return url;
}

async function redirectToHostedUi(path: string): Promise<void> {
  const config = readConfig();
  if (!config) throw new Error("Sign-in is not configured.");

  const verifier = randomVerifier();
  const challenge = base64UrlEncode(await sha256(verifier));
  window.sessionStorage.setItem(PKCE_VERIFIER_KEY, verifier);

  const url = buildHostedUiUrl(config, path, {
    response_type: "code",
    scope: config.scope,
    redirect_uri: config.redirectUri,
    code_challenge_method: "S256",
    code_challenge: challenge,
  });
  window.location.assign(url.toString());
}

export async function beginSignIn(): Promise<void> {
  await redirectToHostedUi("/oauth2/authorize");
}

export async function beginSignUp(): Promise<void> {
  await redirectToHostedUi("/signup");
}

/** Exchanges the authorization code on the callback route for tokens. */
export async function handleAuthCallback(searchParams: URLSearchParams): Promise<void> {
  const config = readConfig();
  if (!config) throw new Error("Sign-in is not configured.");

  if (searchParams.get("error")) {
    throw new Error("Sign-in was not completed.");
  }
  const code = searchParams.get("code");
  const verifier = window.sessionStorage.getItem(PKCE_VERIFIER_KEY);
  if (!code || !verifier) {
    throw new Error("Your sign-in session expired. Please try again.");
  }
  window.sessionStorage.removeItem(PKCE_VERIFIER_KEY);

  const tokens = await requestTokens(
    config,
    new URLSearchParams({
      grant_type: "authorization_code",
      client_id: config.clientId,
      code,
      redirect_uri: config.redirectUri,
      code_verifier: verifier,
    }),
  );
  if (!tokens) throw new Error("Sign-in could not be completed. Please try again.");
  storeTokens(tokens);
}

export function signOut(): void {
  const config = readConfig();
  clearSession();
  if (!config || typeof window === "undefined") return;

  const url = buildHostedUiUrl(config, "/logout", {
    logout_uri: new URL("/", window.location.origin).toString(),
  });
  window.location.assign(url.toString());
}
