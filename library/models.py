import re
from django.db import models
from accounts.models import SteamUser


def normalize_name(name: str) -> str:
    """게임 이름을 소문자+영숫자+한글만 남겨 플랫폼 간 매칭에 사용."""
    return re.sub(r'[^a-z0-9가-힣]', '', name.lower())


class Game(models.Model):
    steam_app_id = models.IntegerField(unique=True, null=True, blank=True)
    name = models.CharField(max_length=256)
    korean_name = models.CharField(max_length=256, blank=True)
    normalized_name = models.CharField(max_length=256, blank=True, db_index=True)
    genres = models.JSONField(default=list)
    tags = models.JSONField(default=list)
    thumbnail_url = models.URLField(blank=True)
    review_score = models.FloatField(default=0.0)

    class Meta:
        indexes = [models.Index(fields=['steam_app_id'])]

    def save(self, *args, **kwargs):
        self.normalized_name = normalize_name(self.name)
        update_fields = kwargs.get('update_fields')
        if update_fields is not None and 'normalized_name' not in update_fields:
            kwargs['update_fields'] = list(update_fields) + ['normalized_name']
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class UserGame(models.Model):
    SOURCE_CHOICES = [('steam', 'Steam')]

    user = models.ForeignKey(SteamUser, on_delete=models.CASCADE, related_name='user_games')
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='user_games')
    playtime_minutes = models.IntegerField(default=0)
    last_played = models.DateTimeField(null=True, blank=True)
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES, default='steam')

    class Meta:
        unique_together = ('user', 'game')
        indexes = [models.Index(fields=['-playtime_minutes'])]

    def __str__(self):
        return f'{self.user} - {self.game}'
