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

# Supported image extensions
SUPPORTED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}


def validate_inputs(local_path: str, is_image: bool = False) -> Path:
    local_file_path = Path(local_path).expanduser().resolve()
    if not local_file_path.exists():
        logger.error(f"File not found: {local_file_path}")
        sys.exit(1)
    if not local_file_path.is_file():
        logger.error(f"Not a file: {local_file_path}")
        sys.exit(1)
    
    # Check file type based on mode
    suffix = local_file_path.suffix.lower()
    if is_image:
        if suffix not in SUPPORTED_IMAGE_EXTENSIONS:
            logger.error(f"Unsupported image format: {suffix}. Supported: {', '.join(SUPPORTED_IMAGE_EXTENSIONS)}")
            sys.exit(1)
    else:
        if suffix != ".pdf":
            logger.warning("The specified file does not have a .pdf extension.")
    
    return local_file_path


def infer_content_type(file_path: Path) -> str:
    guessed_type, _ = mimetypes.guess_type(str(file_path))
    return guessed_type or "application/octet-stream"


def build_s3_key(local_file_path: Path, s3_key: str | None, folder: str | None = None) -> str:
    if s3_key:
        # Normalize leading slash
        return s3_key[1:] if s3_key.startswith("/") else s3_key
    
    # Build key with optional folder prefix
    filename = local_file_path.name
    if folder:
        # Ensure folder doesn't have leading/trailing slashes
        folder = folder.strip("/")
        return f"{folder}/{filename}"
    
    return filename


def upload_file_to_s3(local_file_path: Path, bucket_name: str, object_key: str) -> str:
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

    s3_path = f"s3://{bucket_name}/{object_key}"
    logger.success(f"Upload complete: {s3_path}")
    return s3_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upload a local file (PDF or image) to the configured S3 bucket."
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Absolute path to the local file (e.g., /home/user/docs/file.pdf or /home/user/images/chart.png)",
    )
    parser.add_argument(
        "--key",
        required=False,
        help="S3 object key (path in bucket). Defaults to folder/filename.",
    )
    parser.add_argument(
        "--folder",
        required=False,
        default="dummy_image",
        help="S3 folder to upload to. Defaults to 'dummy_image'.",
    )
    parser.add_argument(
        "--bucket",
        required=False,
        help=(
            "Override bucket name. By default uses settings.AWS_BUCKET_NAME "
            f"(current default: {settings.AWS_BUCKET_NAME})"
        ),
    )
    parser.add_argument(
        "--image",
        action="store_true",
        help="Treat file as an image (validates image extensions)",
    )

    args = parser.parse_args()

    # Auto-detect image mode based on extension if not explicitly set
    file_path = Path(args.file)
    is_image = args.image or file_path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS

    local_file_path = validate_inputs(args.file, is_image=is_image)
    bucket_name = args.bucket or settings.AWS_BUCKET_NAME
    if not bucket_name:
        logger.error("Bucket name is not configured. Set AWS_BUCKET_NAME in your .env or pass --bucket.")
        sys.exit(1)

    object_key = build_s3_key(local_file_path, args.key, folder=args.folder)

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

    s3_path = upload_file_to_s3(local_file_path, bucket_name, object_key)
    
    # Print info for testing the upload-image endpoint
    if is_image:
        logger.info("=" * 60)
        logger.info("To test the /upload-image endpoint, use:")
        logger.info(f'  file_path: "{object_key}"')
        logger.info(f'  file_name: "{local_file_path.name}"')
        logger.info(f'  s3_bucket_name: "{bucket_name}"')
        logger.info("=" * 60)


if __name__ == "__main__":
    # Ensure mimetypes knows about common types
    mimetypes.add_type("application/pdf", ".pdf")
    mimetypes.add_type("image/png", ".png")
    mimetypes.add_type("image/jpeg", ".jpg")
    mimetypes.add_type("image/jpeg", ".jpeg")
    mimetypes.add_type("image/gif", ".gif")
    mimetypes.add_type("image/webp", ".webp")
    mimetypes.add_type("image/bmp", ".bmp")
    main() 
