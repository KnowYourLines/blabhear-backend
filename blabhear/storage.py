import datetime
import os

from google.cloud import storage
from google.oauth2 import service_account

from blabhear.exceptions import InvalidArgumentError

gcp_storage_credentials = {
    "type": "service_account",
    "project_id": os.environ.get("FIREBASE_PROJECT_ID"),
    "private_key_id": os.environ.get("FIREBASE_PRIVATE_KEY_ID"),
    "private_key": os.environ.get("FIREBASE_PRIVATE_KEY").replace("\\n", "\n"),
    "client_email": os.environ.get("FIREBASE_CLIENT_EMAIL"),
    "client_id": os.environ.get("FIREBASE_CLIENT_ID"),
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://accounts.google.com/o/oauth2/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": os.environ.get("FIREBASE_CLIENT_CERT_URL"),
}

credentials = service_account.Credentials.from_service_account_info(
    gcp_storage_credentials
)
storage_client = storage.Client(
    project=gcp_storage_credentials["project_id"], credentials=credentials
)


def generate_upload_signed_url_v4(blob_name):
    bucket = storage_client.bucket(os.environ.get("GCP_BUCKET_NAME"))
    blob = bucket.blob(blob_name)

    url = blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(days=7),
        method="PUT",
        content_type="audio/mp4",
    )
    return url


def generate_download_signed_url_v4(blob_name):
    bucket = storage_client.bucket(os.environ.get("GCP_BUCKET_NAME"))
    blob = bucket.blob(blob_name)

    url = blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(days=7),
        method="GET",
    )
    return url


def copy_existing(
    *,
    source_blob_name,
    destination_blob_name,
):
    if source_blob_name == destination_blob_name:
        raise InvalidArgumentError(
            "Source blob name and destination blob name must be different"
        )
    bucket = storage_client.bucket(os.environ.get("GCP_BUCKET_NAME"))
    source_blob = bucket.blob(source_blob_name)

    # Optional: set a generation-match precondition to avoid potential race conditions
    # and data corruptions. The request to copy is aborted if the object's
    # generation number does not match your precondition. For a destination
    # object that does not yet exist, set the if_generation_match precondition to 0.
    # If the destination object already exists in your bucket, set instead a
    # generation-match precondition using its generation number.
    # There is also an `if_source_generation_match` parameter, which is not used in this example.
    destination_generation_match_precondition = 0

    bucket.copy_blob(
        source_blob,
        bucket,
        destination_blob_name,
        if_generation_match=destination_generation_match_precondition,
    )
