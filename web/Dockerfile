FROM python:3.12-slim

WORKDIR /srv

# 의존성 먼저 설치 (코드만 바꿀 때는 이 단계 캐시 재사용)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 복사
COPY app ./app

EXPOSE 5000

# Socket.IO는 워커 1개 + eventlet
CMD ["gunicorn", "-k", "eventlet", "-w", "1", "-b", "0.0.0.0:5000", "app:app"]