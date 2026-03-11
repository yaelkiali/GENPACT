# app/blob.py
# Azurite connection — local Azure Blob Storage emulator
import json
import os
from datetime import datetime

from azure.storage.blob import BlobServiceClient

AZURE_CONN_STR = os.getenv(
    "AZURE_STORAGE_CONNECTION_STRING",
    # Default Azurite connection string
    "DefaultEndpointsProtocol=http;"
    "AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCXQLv65JcfA==;"
    "BlobEndpoint=http://azurite:10000/devstoreaccount1;"
)

CONTAINER_NAME = "ai-requests"


def get_blob_client() -> BlobServiceClient:
    return BlobServiceClient.from_connection_string(AZURE_CONN_STR)


def ensure_container():
    """Creates the blob container if it does not already exist."""
    client = get_blob_client()
    container = client.get_container_client(CONTAINER_NAME)
    try:
        container.create_container()
    except Exception:
        pass  # Container already exists


def save_request_to_blob(request_id: str, data: dict) -> str:
    """
    Persists the request payload as JSON in blob storage.
    Returns the blob path.
    """
    client = get_blob_client()
    blob_name = f"{datetime.utcnow().strftime('%Y/%m/%d')}/{request_id}.json"
    blob_client = client.get_blob_client(container=CONTAINER_NAME, blob=blob_name)
    blob_client.upload_blob(json.dumps(data, ensure_ascii=False, default=str))
    return blob_name
