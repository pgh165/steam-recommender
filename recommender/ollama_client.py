import requests
from django.conf import settings


def get_recommendation(user_games, deals):
    from recommender.prompt import build_prompt

    prompt = build_prompt(user_games, deals)
    url = f'{settings.OLLAMA_BASE_URL}/api/chat'
    payload = {
        'model': settings.OLLAMA_MODEL,
        'messages': [{'role': 'user', 'content': prompt}],
        'stream': False,
    }
    resp = requests.post(url, json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()['message']['content']


def chat_with_context(messages):
    """messages: [{'role': 'user'|'assistant', 'content': str}, ...]"""
    url = f'{settings.OLLAMA_BASE_URL}/api/chat'
    payload = {
        'model': settings.OLLAMA_MODEL,
        'messages': messages,
        'stream': False,
    }
    resp = requests.post(url, json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()['message']['content']
