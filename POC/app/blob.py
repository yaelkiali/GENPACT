# app/blob.py
# חיבור ל-Azurite — מדמה Azure Blob Storage לוקלית
import json
import os
from datetime import datetime

from azure.storage.blob import BlobServiceClient

AZURE_CONN_STR = os.getenv(
    "AZURE_STORAGE_CONNECTION_STRING",
    # connection string סטנדרטי של Azurite
    "DefaultEndpointsProtocol=http;"
    "AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCXQLv65JcfA==;"
    "BlobEndpoint=http://azurite:10000/devstoreaccount1;"
)

CONTAINER_NAME = "ai-requests"


def get_blob_client() -> BlobServiceClient:
    return BlobServiceClient.from_connection_string(AZURE_CONN_STR)


def ensure_container():
    """יוצר את ה-container אם לא קיים."""
    client = get_blob_client()
    container = client.get_container_client(CONTAINER_NAME)
    try:
        container.create_container()
    except Exception:
        pass  # כבר קיים


def save_request_to_blob(request_id: str, data: dict) -> str:
    """
    שומר את הבקשה כ-JSON ב-blob.
    מחזיר את הנתיב בבלוב.
    """
    client = get_blob_client()
    blob_name = f"{datetime.utcnow().strftime('%Y/%m/%d')}/{request_id}.json"
    blob_client = client.get_blob_client(container=CONTAINER_NAME, blob=blob_name)
    blob_client.upload_blob(json.dumps(data, ensure_ascii=False, default=str))
    return blob_name
