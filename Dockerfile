# Python 3.12 Slim 버전을 베이스로 사용
FROM python:3.12-slim

# 환경 변수 설정 (버퍼링 해제)
ENV PYTHONUNBUFFERED=1

# 필요한 패키지 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_16.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g gitmoji-cli \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리 설정
WORKDIR /app

# 의존성 파일 복사 및 설치 (필요한 경우)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# 기본 실행 명령어 (필요에 따라 변경 가능)
CMD ["bash"]