from collections import defaultdict
from .models import Deal


def get_price_comparison():
    """
    normalized_name이 같은 게임의 딜을 플랫폼별로 묶어 비교.
    Steam 인기 게임이 있으면 우선 표시, 없어도 2개 이상 플랫폼에 걸친 게임은 포함.

    반환 형태:
    [
        {
            'game': Game,
            'steam': Deal or None,
            'others': [Deal, ...],
            'best_deal': Deal,
            'has_cheaper': bool,
        },
        ...
    ]
    """
    all_deals = (
        Deal.objects
        .select_related('game')
        .exclude(game__normalized_name='')
    )

    # normalized_name → {platform: Deal} 매핑 (game도 보존)
    by_norm = defaultdict(dict)
    game_by_norm = {}

    for d in all_deals:
        norm = d.game.normalized_name
        # 같은 norm에서 Steam 게임 우선 (steam_app_id 있는 것)
        if norm not in game_by_norm or d.game.steam_app_id:
            game_by_norm[norm] = d.game
        # 플랫폼당 하나만 (discount_percent 높은 것 우선)
        existing = by_norm[norm].get(d.platform)
        if existing is None or (d.discount_percent or 0) > (existing.discount_percent or 0):
            by_norm[norm][d.platform] = d

    result = []
    for norm, platform_map in by_norm.items():
        if len(platform_map) < 2:
            continue

        game = game_by_norm[norm]
        steam_deal = platform_map.get('steam')
        other_deals = [d for p, d in platform_map.items() if p != 'steam']

        all_group = list(platform_map.values())
        priced = [d for d in all_group if d.sale_price is not None]
        best = min(priced, key=lambda d: d.sale_price) if priced else (steam_deal or other_deals[0])

        steam_price = steam_deal.sale_price if steam_deal else None
        has_cheaper = any(
            d.sale_price is not None and steam_price is not None and d.sale_price < steam_price
            for d in other_deals
        )

        result.append({
            'game': game,
            'steam': steam_deal,
            'others': other_deals,
            'best_deal': best,
            'has_cheaper': has_cheaper,
        })

    # Steam 딜 있는 것 우선, 그 다음 has_cheaper, 그 다음 게임명
    result.sort(key=lambda x: (
        0 if x['steam'] else 1,
        0 if x['has_cheaper'] else 1,
        x['game'].name.lower(),
    ))
    return result
