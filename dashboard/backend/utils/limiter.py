"""Rate limiter 공유 인스턴스 — 순환 임포트 방지를 위해 별도 모듈로 분리."""

from slowapi import Limiter
from slowapi.util import get_remote_address

# 클라이언트 IP 기반 rate limiter
limiter = Limiter(key_func=get_remote_address)
