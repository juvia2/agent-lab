import os
import sys

# SURP_DIR: 테스트 대상 모듈이 있는 폴더 (기본: 원본 inputs/, 수정본: fixed/)
sys.path.insert(0, os.path.abspath(os.environ.get("SURP_DIR", "inputs")))
