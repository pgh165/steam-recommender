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


def get_top100_app_ids():
    """SteamSpy top100in2weeks + top100forever 합산 → [(appid, name, positive, negative), ...]"""
    seen = {}
    for request_type in ('top100in2weeks', 'top100forever'):
        try:
            resp = requests.get(
                'https://steamspy.com/api.php',
                params={'request': request_type},
                timeout=15,
            )
            resp.raise_for_status()
            for v in resp.json().values():
                app_id = int(v['appid'])
                if app_id not in seen:
                    seen[app_id] = (v['name'], int(v.get('positive') or 0), int(v.get('negative') or 0))
        except Exception:
            pass
    return [(app_id, name, pos, neg) for app_id, (name, pos, neg) in seen.items()]
