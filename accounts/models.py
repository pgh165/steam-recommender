from django.db import models
from django.contrib.auth.models import User


class SteamUser(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='steam_profile')
    steam_id = models.CharField(max_length=64, unique=True)
    display_name = models.CharField(max_length=128, blank=True)
    avatar_url = models.URLField(blank=True)
    profile_updated_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'{self.display_name} ({self.steam_id})'
