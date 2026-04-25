from django.core.management.base import BaseCommand
from deals.crawler import fetch_steam_deals, fetch_directgames_deals


class Command(BaseCommand):
    help = '할인 정보 수집 (Steam + 다이렉트게임즈)'

    def handle(self, *args, **kwargs):
        results = [
            ('Steam',        fetch_steam_deals),
            ('다이렉트게임즈', fetch_directgames_deals),
        ]
        total = 0
        for label, fn in results:
            try:
                n = fn()
                self.stdout.write(f'{label}: {n}개')
                total += n
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'{label} 수집 실패: {e}'))

        self.stdout.write(self.style.SUCCESS(f'총 {total}개 할인 정보 업데이트 완료'))
