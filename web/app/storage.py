import os
import uuid

import boto3

STORAGE = os.environ.get("STORAGE", "s3")          # s3 | local
BUCKET = os.environ.get("S3_BUCKET", "")
REGION = os.environ.get("AWS_REGION", "ap-southeast-2")
LOCAL_DIR = "/data/uploads"

MAX_BYTES = 5 * 1024 * 1024
# 확장자 대신 파일 앞부분(매직 바이트)으로 실제 이미지인지 확인
SIGNATURES = {
    b"\xff\xd8\xff": ("image/jpeg", ".jpg"),
    b"\x89PNG": ("image/png", ".png"),
}   

_s3 = None


def _client():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3", region_name=REGION)
    return _s3


class UploadError(Exception):
    pass


def _inspect(file):
    """크기와 형식을 검사하고 (content_type, ext)를 돌려준다."""
    file.stream.seek(0, os.SEEK_END)
    size = file.stream.tell()
    file.stream.seek(0)
    if size == 0:
        raise UploadError("사진을 선택해 주세요.")
    if size > MAX_BYTES:
        raise UploadError("사진은 5MB 이하만 가능합니다.")

    head = file.stream.read(8)
    file.stream.seek(0)
    for sig, info in SIGNATURES.items():
        if head.startswith(sig):
            return info
    raise UploadError("jpg 또는 png 이미지만 업로드할 수 있습니다.")


def save_image(file):
    """사진을 저장하고 (key, url)을 반환. 실패하면 UploadError."""
    content_type, ext = _inspect(file)
    key = f"items/{uuid.uuid4().hex}{ext}"       # 파일명은 서버에서 새로 생성

    if STORAGE == "s3":
        try:
            _client().upload_fileobj(
                file.stream, BUCKET, key, ExtraArgs={"ContentType": content_type}
            )
        except Exception as e:
            raise UploadError("사진 업로드에 실패했습니다.") from e
        url = f"https://{BUCKET}.s3.{REGION}.amazonaws.com/{key}"
    else:
        os.makedirs(os.path.join(LOCAL_DIR, "items"), exist_ok=True)
        file.save(os.path.join(LOCAL_DIR, key))
        url = f"/api/uploads/{key}"
    return key, url


def delete_image(key):
    """사진 삭제. 이미 없으면 조용히 넘어간다 (T3-2 자동 정리에서 사용)."""
    if not key:
        return
    try:
        if STORAGE == "s3":
            _client().delete_object(Bucket=BUCKET, Key=key)
        else:
            os.remove(os.path.join(LOCAL_DIR, key))
    except (FileNotFoundError, Exception):
        pass