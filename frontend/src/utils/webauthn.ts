/**
 * WebAuthn Browser API helpers.
 *
 * Bridges the gap between the server's JSON format and the browser's
 * navigator.credentials API which expects ArrayBuffer objects.
 */

export function isWebAuthnSupported(): boolean {
  return !!window.PublicKeyCredential;
}

// ─── Base64URL Helpers ───

function base64URLToBuffer(base64url: string): ArrayBuffer {
  const base64 = base64url.replace(/-/g, '+').replace(/_/g, '/');
  const pad = base64.length % 4 === 0 ? '' : '='.repeat(4 - (base64.length % 4));
  const binary = atob(base64 + pad);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

function bufferToBase64URL(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

// ─── Registration ───

export function prepareRegistrationOptions(serverOptions: any): PublicKeyCredentialCreationOptions {
  const options = { ...serverOptions };

  // Convert challenge from base64url to ArrayBuffer
  options.challenge = base64URLToBuffer(options.challenge);

  // Convert user.id from base64url to ArrayBuffer
  if (options.user?.id) {
    options.user = { ...options.user, id: base64URLToBuffer(options.user.id) };
  }

  // Convert excludeCredentials ids
  if (options.excludeCredentials) {
    options.excludeCredentials = options.excludeCredentials.map((c: any) => ({
      ...c,
      id: base64URLToBuffer(c.id),
    }));
  }

  return options as PublicKeyCredentialCreationOptions;
}

export function serializeRegistrationCredential(credential: PublicKeyCredential): any {
  const response = credential.response as AuthenticatorAttestationResponse;
  return {
    id: credential.id,
    rawId: bufferToBase64URL(credential.rawId),
    type: credential.type,
    response: {
      attestationObject: bufferToBase64URL(response.attestationObject),
      clientDataJSON: bufferToBase64URL(response.clientDataJSON),
    },
  };
}

// ─── Authentication ───

export function prepareAuthenticationOptions(serverOptions: any): PublicKeyCredentialRequestOptions {
  const options = { ...serverOptions };

  options.challenge = base64URLToBuffer(options.challenge);

  if (options.allowCredentials) {
    options.allowCredentials = options.allowCredentials.map((c: any) => ({
      ...c,
      id: base64URLToBuffer(c.id),
    }));
  }

  return options as PublicKeyCredentialRequestOptions;
}

export function serializeAuthenticationCredential(credential: PublicKeyCredential): any {
  const response = credential.response as AuthenticatorAssertionResponse;
  return {
    id: credential.id,
    rawId: bufferToBase64URL(credential.rawId),
    type: credential.type,
    response: {
      authenticatorData: bufferToBase64URL(response.authenticatorData),
      clientDataJSON: bufferToBase64URL(response.clientDataJSON),
      signature: bufferToBase64URL(response.signature),
      userHandle: response.userHandle ? bufferToBase64URL(response.userHandle) : null,
    },
  };
}
