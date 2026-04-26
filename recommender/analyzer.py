"""사용자 라이브러리와 후보 딜을 사전 분석/점수화하는 모듈."""
from collections import Counter


_PLAY_MODE_KEYWORDS = {
    'multi': ['멀티플레이어', '온라인 PvP', '온라인 협동', 'PvP', 'MMO', 'Multi-player'],
    'coop': ['협동', '온라인 협동', '로컬 협동', 'Co-op'],
    'single': ['싱글 플레이어', 'Single-player'],
}


def _extract_tag_descs(tags):
    if not tags:
        return []
    if isinstance(tags[0], dict):
        return [t.get('description', '') for t in tags]
    return list(tags)


def _detect_play_modes(tag_descs):
    modes = set()
    for kind, kws in _PLAY_MODE_KEYWORDS.items():
        if any(kw in d for d in tag_descs for kw in kws):
            modes.add(kind)
    return modes


def analyze_user(user_games):
    """플레이 기록을 다차원 분석.

    user_games: List[{name, playtime_minutes, genres, tags}]
    반환: dict — top_genres, heavy_ratio, multi_ratio, single_ratio, diversity, summary_text
    """
    if not user_games:
        return None

    total_playtime = sum(g['playtime_minutes'] for g in user_games) or 1

    # 장르 가중치 (플레이타임 기준)
    genre_weights = Counter()
    for g in user_games:
        for genre in (g.get('genres') or []):
            genre_weights[genre] += g['playtime_minutes']
    top_genres = [g for g, _ in genre_weights.most_common(5)]

    # 헤비/캐주얼: 100시간(=6000분) 이상 게임 비율
    heavy_count = sum(1 for g in user_games if g['playtime_minutes'] >= 6000)
    heavy_ratio = heavy_count / len(user_games)

    # 멀티/싱글: 플레이타임 가중치
    multi_pt = single_pt = 0
    for g in user_games:
        modes = _detect_play_modes(_extract_tag_descs(g.get('tags')))
        if 'multi' in modes or 'coop' in modes:
            multi_pt += g['playtime_minutes']
        if 'single' in modes:
            single_pt += g['playtime_minutes']
    classified = multi_pt + single_pt or 1
    multi_ratio = multi_pt / classified
    single_ratio = single_pt / classified

    # 장르 다양성: 상위 1개 장르가 전체 플레이타임에서 차지하는 비중 (낮을수록 다양)
    top_genre_share = (genre_weights.most_common(1)[0][1] / total_playtime) if genre_weights else 0
    diversity = 1 - top_genre_share  # 0~1, 높을수록 다양

    # 사람이 읽을 수 있는 요약 텍스트 (LLM 프롬프트에 직접 삽입)
    parts = []
    if top_genres:
        parts.append(f"선호 장르 상위: {', '.join(top_genres[:3])}")
    if heavy_ratio >= 0.3:
        parts.append(f"헤비 게이머 성향 (100시간+ 게임 {heavy_count}개)")
    elif heavy_ratio <= 0.1:
        parts.append("주로 가볍게 즐기는 편")
    if multi_ratio > 0.6:
        parts.append(f"멀티플레이 위주 ({multi_ratio*100:.0f}%)")
    elif single_ratio > 0.6:
        parts.append(f"싱글플레이 위주 ({single_ratio*100:.0f}%)")
    else:
        parts.append("멀티/싱글 모두 즐김")
    if diversity > 0.7:
        parts.append("장르 다양성 높음")
    elif diversity < 0.4:
        parts.append("특정 장르 집중")

    summary_text = ' · '.join(parts)

    return {
        'top_genres': top_genres,
        'heavy_ratio': heavy_ratio,
        'multi_ratio': multi_ratio,
        'single_ratio': single_ratio,
        'diversity': diversity,
        'summary_text': summary_text,
    }


def score_deal(deal_dict, profile, user_owned_genre_set):
    """단일 후보 딜을 사용자 프로필 기준으로 점수화."""
    score = 0.0

    # 장르 매칭 (상위 장르와 겹치는 개수 × 가중치)
    deal_genres = set(deal_dict.get('genres') or [])
    matched_top = sum(1 for g in profile['top_genres'][:3] if g in deal_genres)
    score += matched_top * 3.0
    matched_owned = len(deal_genres & user_owned_genre_set)
    score += min(matched_owned, 3) * 0.5

    # 평점 (0.0~1.0 → 0~3점)
    score += (deal_dict.get('review_score') or 0) * 3.0

    # 할인율 보너스 (할인 중인 게임 우대, 최대 1점)
    disc = deal_dict.get('discount_percent') or 0
    score += min(disc / 50, 1.0)

    # 멀티/싱글 매칭
    modes = _detect_play_modes(_extract_tag_descs(deal_dict.get('tags')))
    if profile['multi_ratio'] > 0.6 and ('multi' in modes or 'coop' in modes):
        score += 1.5
    elif profile['single_ratio'] > 0.6 and 'single' in modes:
        score += 1.5

    return score
