# 연구실 샌드박스 이미지: 언어학·언어인지과학·언어모델 실험용 CPU 환경 (맥 Apple Silicon 에서는 linux/arm64)
FROM python:3.12-slim

ENV PIP_NO_CACHE_DIR=1 PYTHONUNBUFFERED=1 DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 과학 계산·통계·시각화
RUN pip install numpy scipy pandas scikit-learn statsmodels matplotlib seaborn pyyaml tqdm pytest

# 언어모델 (CPU 빌드)
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install transformers datasets tokenizers accelerate sentencepiece safetensors

# 언어학·인지과학 도구: 한국어 형태소 분석(kiwipiepy), 일반 NLP(nltk), EEG/MEG 분석(mne)
RUN pip install kiwipiepy nltk mne

WORKDIR /work
