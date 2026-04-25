import json
import requests
from django.conf import settings

# 연결 수립 타임아웃 / 청크 수신 타임아웃(스트리밍 시 청크 간 최대 대기)
_CONNECT_TIMEOUT = 10
_READ_TIMEOUT    = 300   # 26B 모델 기준 청크 간 최대 대기


def _stream_chat(messages) -> str:
    """Ollama streaming API로 응답 전체를 모아 반환."""
    url = f'{settings.OLLAMA_BASE_URL}/api/chat'
    payload = {
        'model': settings.OLLAMA_MODEL,
        'messages': messages,
        'stream': True,
    }
    parts = []
    with requests.post(
        url, json=payload,
        timeout=(_CONNECT_TIMEOUT, _READ_TIMEOUT),
        stream=True,
    ) as resp:
        resp.raise_for_status()
        for raw_line in resp.iter_lines():
            if not raw_line:
                continue
            chunk = json.loads(raw_line)
            parts.append(chunk.get('message', {}).get('content', ''))
            if chunk.get('done'):
                break
    return ''.join(parts)


def get_recommendation(user_games, deals):
    from recommender.prompt import build_prompt
    prompt = build_prompt(user_games, deals)
    return _stream_chat([{'role': 'user', 'content': prompt}])


def chat_with_context(messages):
    """messages: [{'role': 'user'|'assistant', 'content': str}, ...]"""
    return _stream_chat(messages)
