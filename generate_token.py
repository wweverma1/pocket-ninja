import os
from google_auth_oauthlib.flow import InstalledAppFlow

# 1. Setup your Client ID and Secret here or use env vars
CLIENT_ID = "YOUR_CLIENT_ID_HERE"
CLIENT_SECRET = "YOUR_CLIENT_SECRET_HERE"

# 2. Scopes required for uploading to Drive
SCOPES = ['https://www.googleapis.com/auth/drive.file']

def main():
    if CLIENT_ID == "YOUR_CLIENT_ID_HERE":
        print("Please edit the script and add your Client ID and Secret.")
        return

    # Create the flow
    flow = InstalledAppFlow.from_client_config(
        {
            "web": {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        SCOPES
    )

    # Run local server to listen for the callback
    creds = flow.run_local_server(port=8080)

    print("\n" + "="*50)
    print("SUCCESS! Here is your Refresh Token:")
    print("="*50 + "\n")
    print(creds.refresh_token)
    print("\n" + "="*50)
    print("Add this to your .env file as GOOGLE_REFRESH_TOKEN")

if __name__ == '__main__':
    main()