from google_auth_oauthlib.flow import InstalledAppFlow

CLIENT_ID = "YOUR_CLIENT_ID_HERE"
CLIENT_SECRET = "YOUR_CLIENT_SECRET_HERE"

SCOPES = ['https://www.googleapis.com/auth/drive.file']


def main():
    if CLIENT_ID == "YOUR_CLIENT_ID_HERE":
        print("Please edit the script and add your Client ID and Secret.")
        return

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

    creds = flow.run_local_server(port=5000)

    print("\n" + "=" * 50)
    print("SUCCESS! Here is your Refresh Token:")
    print("=" * 50 + "\n")
    print(creds.refresh_token)
    print("\n" + "=" * 50)
    print("Add this to your .env file as GOOGLE_REFRESH_TOKEN")


if __name__ == '__main__':
    main()
