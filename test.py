#!/usr/bin/env python3
import argparse
import mimetypes
import os
import sys
from pathlib import Path

from loguru import logger

# Reuse existing configuration and S3 session
from app.config import settings
from app.utils.s3 import session


def validate_inputs(local_path: str) -> Path:
    local_file_path = Path(local_path).expanduser().resolve()
    if not local_file_path.exists():
        logger.error(f"File not found: {local_file_path}")
        sys.exit(1)
    if not local_file_path.is_file():
        logger.error(f"Not a file: {local_file_path}")
        sys.exit(1)
    # Basic check for PDF by extension; content-type will be set via mimetypes
    if local_file_path.suffix.lower() != ".pdf":
        logger.warning("The specified file does not have a .pdf extension.")
    return local_file_path


def infer_content_type(file_path: Path) -> str:
    guessed_type, _ = mimetypes.guess_type(str(file_path))
    return guessed_type or "application/octet-stream"


def build_s3_key(local_file_path: Path, s3_key: str | None) -> str:
    if s3_key:
        # Normalize leading slash
        return s3_key[1:] if s3_key.startswith("/") else s3_key
    # Default: put at root using the filename
    return local_file_path.name


def upload_file_to_s3(local_file_path: Path, bucket_name: str, object_key: str) -> None:
    s3 = session.client("s3")
    content_type = infer_content_type(local_file_path)
    logger.info(
        f"Uploading to S3 | bucket={bucket_name} key={object_key} content_type={content_type}"
    )

    extra_args = {"ContentType": content_type}

    try:
        s3.upload_file(
            Filename=str(local_file_path),
            Bucket=bucket_name,
            Key=object_key,
            ExtraArgs=extra_args,
        )
    except Exception as e:
        logger.exception(f"Upload failed: {e}")
        sys.exit(1)

    logger.success(
        f"Upload complete: s3://{bucket_name}/{object_key}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upload a local PDF (or any file) to the configured S3 bucket."
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Absolute path to the local file (e.g., /home/user/docs/file.pdf)",
    )
    parser.add_argument(
        "--key",
        required=False,
        help="S3 object key (path in bucket). Defaults to the local filename at bucket root.",
    )
    parser.add_argument(
        "--bucket",
        required=False,
        help=(
            "Override bucket name. By default uses settings.AWS_BUCKET_NAME "
            f"(current default: {settings.AWS_BUCKET_NAME})"
        ),
    )

    args = parser.parse_args()

    local_file_path = validate_inputs(args.file)
    bucket_name = args.bucket or settings.AWS_BUCKET_NAME
    if not bucket_name:
        logger.error("Bucket name is not configured. Set AWS_BUCKET_NAME in your .env or pass --bucket.")
        sys.exit(1)

    object_key = build_s3_key(local_file_path, args.key)

    # Log effective AWS configuration surface (safe subset)
    logger.info(
        (
            "Using AWS configuration: region={region} env={env} bucket={bucket}"
        ).format(
            region=settings.AWS_REGION,
            env=settings.ENVIRONMENT,
            bucket=bucket_name,
        )
    )

    upload_file_to_s3(local_file_path, bucket_name, object_key)


if __name__ == "__main__":
    # Ensure mimetypes knows about PDF on some systems
    mimetypes.add_type("application/pdf", ".pdf")
    main() 