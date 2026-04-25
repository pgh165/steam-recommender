import time
import requests
from django.conf import settings


def get_owned_games(steam_id):
    url = 'https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/'
    params = {
        'key': settings.STEAM_API_KEY,
        'steamid': steam_id,
        'include_appinfo': 'true',
        'include_played_free_games': 'true',
    }
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return data.get('response', {}).get('games', [])


def get_app_details(app_id):
    url = f'https://store.steampowered.com/api/appdetails'
    params = {'appids': app_id, 'cc': 'kr', 'l': 'korean'}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    app_data = data.get(str(app_id), {})
    if not app_data.get('success'):
        return {}
    return app_data.get('data', {})


def get_steam_deals():
    url = 'https://store.steampowered.com/api/featuredcategories'
    resp = requests.get(url, params={'cc': 'kr'}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    items = []
    for category in ('specials', 'top_sellers'):
        for item in data.get(category, {}).get('items', []):
            item['_category'] = category
            items.append(item)
    return items


def get_store_top_sellers(count=100):
    """Steam 스토어 topsellers + toprated 합산 → [(appid, name), ...] (중복 제거)"""
    import re
    seen = {}
    for filt in ('topsellers', 'toprated'):
        try:
            resp = requests.get(
                'https://store.steampowered.com/search/results/',
                params={'filter': filt, 'cc': 'KR', 'count': count, 'json': '1'},
                timeout=15,
            )
            resp.raise_for_status()
            for it in resp.json().get('items', []):
                m = re.search(r'/apps/(\d+)/', it.get('logo', ''))
                if m:
                    app_id = int(m.group(1))
                    if app_id not in seen:
                        seen[app_id] = it.get('name', '')
        except Exception:
            pass
    return list(seen.items())
