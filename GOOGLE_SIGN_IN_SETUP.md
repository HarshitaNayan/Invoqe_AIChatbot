# Enable real Google sign-in for Hynex

The code is implemented, but Google must issue OAuth credentials for YOUR application before the Google button can work. A Gemini API key is not a Google sign-in client secret. Do not reuse it for OAuth.

Google handles account selection, password entry and any two-step verification on Google's own website. Hynex never asks for, receives, or stores a Google password. The local username/password option is a separate Hynex account and is retained from the previous update.

## One-time local setup

1. Open https://console.cloud.google.com/ and select or create the project you want to use for Hynex.
2. Open Google Auth Platform (or APIs & Services → OAuth consent screen). Configure the app name **Hynex**, your support email, developer contact email, and intended audience. If the app is in testing, add your own Google email and any people testing it as test users.
3. In Clients / Credentials, create an **OAuth client ID** with application type **Web application**.
4. Add this exact authorized redirect URI:

```
http://127.0.0.1:8000/api/auth/google/callback
```

5. Copy the client ID and client secret into your PRIVATE existing `.env` file. Keep its existing Gemini settings and append these lines, replacing the placeholders yourself:

```dotenv
GOOGLE_CLIENT_ID=PASTE_YOUR_OAUTH_CLIENT_ID
GOOGLE_CLIENT_SECRET=PASTE_YOUR_OAUTH_CLIENT_SECRET
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/api/auth/google/callback
HYNEX_COOKIE_SECURE=0
HYNEX_REQUIRE_LOGIN=0
```

6. Install the update's dependencies and restart the server from the project folder:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

7. Open **http://127.0.0.1:8000** (use exactly that origin), press Ctrl+F5, open **Account**, and click **Continue with Google**. Choose your account on Google's page. After success, Google redirects you to Hynex and the sidebar shows the signed-in account.

Do not share the client secret or your `.env`. Do not type your Google password into Hynex's local password box. Credentials and this callback URI must belong to the same OAuth client configuration. `localhost` and `127.0.0.1` are different browser origins; do not switch between them halfway through sign-in.

The Google button remains disabled until all OAuth settings are configured. This is intentional; an imitation Google login would be unsafe and would not authenticate anyone.

## Require login before using Hynex

Guest mode remains available by default to preserve the existing app behaviour. To require every visitor to sign in before chat, uploads or study tools, set:

```dotenv
HYNEX_REQUIRE_LOGIN=1
```

Restart the server. The browser opens the account dialog and backend routes independently enforce sign-in. Hiding a button alone is not used as an authorization mechanism.

Whether guest mode is enabled or disabled, saved account chats, uploads and ratings are accessible only to their owner. The server derives owner identity from the verified session, never from a user ID submitted in a request.

## Publishing on a real domain

Use a hosting service with persistent storage and HTTPS. Add your actual HTTPS callback URI in Google Cloud and set the EXACT same URL in `.env`:

```dotenv
GOOGLE_REDIRECT_URI=https://YOUR-ACTUAL-DOMAIN/api/auth/google/callback
HYNEX_COOKIE_SECURE=1
HYNEX_REQUIRE_LOGIN=1
```

Replace YOUR-ACTUAL-DOMAIN with your actual host. Do not leave this placeholder in the configuration. Ensure your trusted reverse proxy passes the correct HTTPS scheme to Uvicorn; the origin protections must see the public origin. Configure trusted proxy forwarding at the host rather than accepting forwarded headers from everyone.

Public Google sign-in is disabled by the server when secure cookies are not enabled. Configure Google's app audience/publication requirements as appropriate for the users you intend to support. HTTPS is mandatory outside local development. Back up the private SQLite database; an ephemeral hosting disk will not preserve accounts.

## Protections included

- Google OpenID Connect authorization-code flow; Google tokens are verified on the backend using Google's official `google-auth` library.
- Google ID-token signature, issuer, client audience and expiry verification; explicit nonce, verified-email and authorized-party checks.
- PKCE S256 with a server-held verifier.
- Random browser-bound OAuth state, single-use flows, ten-minute expiry, HttpOnly SameSite=Lax flow cookie.
- A new random Hynex session after success, with HttpOnly SameSite=Strict cookies, Secure cookies on HTTPS and seven-day expiry. Google access/refresh/ID tokens are not retained in the database.
- Account ownership based on Google's stable `sub`, not a client-supplied email. Google accounts and existing local accounts are not silently linked by email.
- Server-side ownership checks for chats, private documents and feedback; cross-origin write protection; basic sign-in attempt throttling; frame blocking, content security policy and HTTPS security headers.
- Private database and `.env` remain outside the public static directory. OAuth callback query parameters are redacted from Uvicorn access logs. Configure any upstream proxy to redact callback queries too.

These protections reduce risk, but no application can be guaranteed unhackable. Do not describe this small-project login system as audited or production-certified. Local accounts still have no password-recovery or email-verification flow. All sessions and data are managed by this app; this does not implement Google's cross-account security event service.

## Test and troubleshoot

- **redirect_uri_mismatch:** compare the callback URI in Google Cloud with `GOOGLE_REDIRECT_URI`, including scheme, host, port and path.
- **Access blocked / tester restriction:** check the app audience, test-user list and consent configuration in Google Cloud.
- **Invalid or expired session:** start again from Account; keep the same browser and origin, allow cookies and complete within ten minutes.
- **Sign-in failed:** check OAuth configuration, the computer's clock and outbound access to Google. Error pages deliberately do not display secret provider responses.
- **Old interface:** Ctrl+F5 and verify the new `static/features.js` was copied.

Automated tests cover state/cookie failure, expired/replayed flows, bad nonce, signature-verifier rejection, session creation/logout, subject-based account isolation, the optional login gate, and local creator identity. Google exchange and verification were simulated in those tests. A real end-to-end Google login still requires your own OAuth credentials and browser test.

Official references:
- https://developers.google.com/identity/openid-connect/openid-connect
- https://developers.google.com/identity/sign-in/web/backend-auth
- https://google-auth.readthedocs.io/en/latest/reference/google.oauth2.id_token.html

## Creator identity

The chat endpoint answers common direct creator questions locally with:

> Hynex was created by Harshita Nayan.

This works even without Gemini connectivity. The same creator identity is included in the model's system instruction for other phrasing. Questions specifically about the underlying model provider can still truthfully identify Google/Gemini; Harshita Nayan is identified as the creator of the Hynex application.
