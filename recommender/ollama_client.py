import json
import requests
from django.conf import settings

_CONNECT_TIMEOUT = 10
_READ_TIMEOUT    = 300


def _iter_chat(messages, *, num_predict=1000):
    """Ollama streaming API 청크를 하나씩 yield하는 제너레이터."""
    url = f'{settings.OLLAMA_BASE_URL}/api/chat'
    payload = {
        'model': settings.OLLAMA_MODEL,
        'messages': messages,
        'stream': True,
        'think': False,                   # thinking 모델의 사고 단계 비활성화 (gemma4:e4b 등)
        'options': {
            'num_predict': num_predict,
            'num_ctx': 4096,
            'temperature': 0.7,
        },
    }
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
            token = chunk.get('message', {}).get('content', '')
            if token:
                yield token
            if chunk.get('done'):
                break


def _collect_chat(messages) -> str:
    """_iter_chat을 모아 문자열로 반환 (채팅용)."""
    return ''.join(_iter_chat(messages))


def get_recommendation(user_games, deals, profile=None):
    from recommender.prompt import build_prompt
    prompt = build_prompt(user_games, deals, profile)
    return _collect_chat([{'role': 'user', 'content': prompt}])


def chat_with_context(messages):
    return _collect_chat(messages)
