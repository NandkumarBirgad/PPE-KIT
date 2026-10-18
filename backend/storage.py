import os
import time
import base64
import uuid
import cloudinary
import cloudinary.uploader
import cloudinary.api
from config import Config

# Configure Cloudinary
if Config.CLOUDINARY_CLOUD_NAME and Config.CLOUDINARY_API_KEY and Config.CLOUDINARY_API_SECRET:
    cloudinary.config(
        cloud_name=Config.CLOUDINARY_CLOUD_NAME,
        api_key=Config.CLOUDINARY_API_KEY,
        api_secret=Config.CLOUDINARY_API_SECRET,
        secure=True
    )
    _cloudinary_enabled = True
    print(f"[Cloudinary] Storage Connected! Cloud Name: {Config.CLOUDINARY_CLOUD_NAME}")
else:
    _cloudinary_enabled = False
    print("[Cloudinary] Credentials not configured. Using local disk storage.")

def is_cloudinary_enabled():
    return _cloudinary_enabled

def upload_evidence_image(image_input, folder="ppe_violations"):
    """
    Uploads an evidence image (base64 data URI, raw base64, or file object)
    to Cloudinary cloud storage.
    Falls back to local disk storage if Cloudinary fails or is unavailable.
    Returns: URL or relative path to the stored image.
    """
    if not image_input:
        return None

    # 1. Try uploading to Cloudinary
    if _cloudinary_enabled:
        try:
            # If base64 data without URI prefix, add prefix
            upload_payload = image_input
            if isinstance(image_input, str):
                if not image_input.startswith("data:image"):
                    upload_payload = f"data:image/jpeg;base64,{image_input}"

            upload_result = cloudinary.uploader.upload(
                upload_payload,
                folder=folder,
                resource_type="image",
                transformation=[
                    {"quality": "auto", "fetch_format": "auto"}
                ]
            )
            secure_url = upload_result.get("secure_url")
            if secure_url:
                return secure_url
        except Exception as e:
            print(f"[Warning] Cloudinary upload error: {e}. Falling back to local storage.")

    # 2. Fallback to Local Disk Storage
    try:
        os.makedirs(Config.EVIDENCE_FOLDER, exist_ok=True)
        filename = f"violation_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}.jpg"
        filepath = os.path.join(Config.EVIDENCE_FOLDER, filename)

        if isinstance(image_input, str):
            clean_b64 = image_input
            if clean_b64.startswith("data:image"):
                clean_b64 = clean_b64.split(",")[1]
            img_bytes = base64.b64decode(clean_b64)
            with open(filepath, "wb") as f:
                f.write(img_bytes)
        elif hasattr(image_input, "save"):
            image_input.save(filepath)
        elif hasattr(image_input, "read"):
            with open(filepath, "wb") as f:
                f.write(image_input.read())

        return f"/uploads/evidence/{filename}"
    except Exception as e:
        print(f"[Warning] Failed to save image locally: {e}")
        # Return original base64 as ultimate fallback
        return image_input
