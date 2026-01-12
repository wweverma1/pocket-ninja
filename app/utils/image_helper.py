import io
import os
import json
import requests
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from PIL import Image


def optimize_image_stream(file_storage, max_dimension=1500, quality=80) -> bytes:
    try:
        file_storage.seek(0, os.SEEK_END)
        file_size = file_storage.tell()
        file_storage.seek(0)

        if file_size < 1 * 1024 * 1024 and file_storage.mimetype == 'image/webp':
            return file_storage.read()

        img = Image.open(file_storage)

        if img.mode in ('RGBA', 'LA'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1])
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        width, height = img.size
        max_side = max(width, height)
        if max_side > max_dimension:
            scale_factor = max_dimension / max_side
            new_width = int(width * scale_factor)
            new_height = int(height * scale_factor)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format="WEBP", quality=quality, method=4)
        return buffer.getvalue()

    except Exception as e:
        print(f"Optimization Error: {e}")
        return None


def upload_receipt_to_drive(image_bytes: bytes, receipt_id: str):
    try:
        client_id = os.getenv("GOOGLE_DRIVE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_DRIVE_CLIENT_SECRET")
        refresh_token = os.getenv("GOOGLE_DRIVE_REFRESH_TOKEN")
        folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

        if not all([client_id, client_secret, refresh_token, folder_id]):
            print("Google Drive Upload Skipped: Missing configuration.")
            return

        creds = Credentials(
            None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret
        )

        creds.refresh(Request())

        filename = f"{receipt_id}.webp"

        metadata = {
            "name": filename,
            "parents": [folder_id]
        }

        headers = {
            "Authorization": f"Bearer {creds.token}"
        }

        files = {
            'data': ('metadata', json.dumps(metadata), 'application/json; charset=UTF-8'),
            'file': (filename, io.BytesIO(image_bytes), 'image/webp')
        }

        response = requests.post(
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
            headers=headers,
            files=files
        )

        if response.status_code == 200:
            print(f"Successfully uploaded receipt to Drive: {response.json().get('id')}")
        else:
            print(f"Failed to upload to Drive: {response.status_code} - {response.text}")

    except Exception as e:
        print(f"Error uploading to Google Drive: {e}")
