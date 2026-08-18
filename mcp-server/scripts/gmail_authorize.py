"""One-time interactive Gmail OAuth authorization (Phase 17).

Run this ONCE, locally, after creating a Google Cloud OAuth client - see
README.md's "Email (Gmail)" section for the exact Google Cloud Console
steps. This opens your browser, asks you to log into the Gmail account you
want the MCP server to use, and shows Google's consent screen for two
scopes: sending email and reading email (read-only - this app can never
delete or modify anything in your inbox).

After you approve, this prints the GMAIL_* lines to add to mcp-server/.env.
The refresh token is the sensitive part - it's what lets the server get new
access tokens indefinitely without you logging in again. It is NEVER sent
anywhere except Google's own token endpoint, and this script does not write
it to any file or log for you automatically - you copy it into .env
yourself, so you always know exactly where your one copy of it lives.

Usage:
    uv run python scripts/gmail_authorize.py
"""
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]


def main() -> None:
    print("This will open your browser to sign in to Google and authorize this app.")
    print("Use the Gmail account you want the MCP server's email tools to act as.\n")

    client_id = input("OAuth Client ID (from Google Cloud Console): ").strip()
    client_secret = input("OAuth Client Secret: ").strip()

    if not client_id or not client_secret:
        print("Both the Client ID and Client Secret are required.", file=sys.stderr)
        sys.exit(1)

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    # Spins up a temporary local server on a random port and opens your
    # default browser to Google's consent screen - this is Google's own
    # recommended flow for CLI/desktop apps (no public redirect URI to
    # register or expose, unlike the main chatbot's web login flow).
    credentials = flow.run_local_server(port=0)

    print("\nAuthorization successful.\n")
    print("Add these lines to mcp-server/.env:\n")
    print(f"GMAIL_CLIENT_ID={client_id}")
    print(f"GMAIL_CLIENT_SECRET={client_secret}")
    print(f"GMAIL_REFRESH_TOKEN={credentials.refresh_token}")
    print("GMAIL_USER_EMAIL=<the Gmail address you just signed in with>")
    print(
        "\nIf GMAIL_REFRESH_TOKEN is blank above, Google didn't issue a new one - this "
        "happens if this exact app was already authorized once before. Go to "
        "https://myaccount.google.com/permissions, remove access for this app's name, "
        "then re-run this script."
    )


if __name__ == "__main__":
    main()
