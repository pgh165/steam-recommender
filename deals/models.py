from django.db import models
from library.models import Game


class Deal(models.Model):
    PLATFORM_CHOICES = [
        ('steam', 'Steam'),
        ('directgames', '다이렉트게임즈'),
    ]

    CATEGORY_CHOICES = [
        ('specials', '할인 특가'),
        ('top_sellers', '인기 게임'),
        ('popular', '인기 게임'),
    ]

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='deals')
    platform = models.CharField(max_length=16, choices=PLATFORM_CHOICES, default='steam')
    category = models.CharField(max_length=16, choices=CATEGORY_CHOICES, default='specials')
    original_price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    sale_price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    discount_percent = models.IntegerField(default=0)
    deal_url = models.URLField(blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('game', 'platform')
        indexes = [models.Index(fields=['-discount_percent'])]

    def __str__(self):
        return f'{self.game.name} -{self.discount_percent}% ({self.platform})'
