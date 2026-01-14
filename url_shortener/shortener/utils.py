import random
import string
from datetime import timedelta
from django.utils import timezone
from django.db.models import Q
from .models import ShortenedURL, DailyStats

def generate_short_code(length=6, existing_codes=None):
    """Генерирует уникальный короткий код"""
    chars = string.ascii_letters + string.digits
    
    if existing_codes is None:
        existing_codes = ShortenedURL.objects.values_list('short_code', flat=True)
    
    while True:
        code = ''.join(random.choice(chars) for _ in range(length))
        if code not in existing_codes:
            return code

def cleanup_expired_urls():
    """Очистка просроченных ссылок"""
    expired_urls = ShortenedURL.objects.filter(
        Q(expires_at__lt=timezone.now()) | 
        Q(is_active=False)
    )
    
    count = expired_urls.count()
    expired_urls.delete()
    
    return count

def update_daily_stats():
    """Обновление ежедневной статистики"""
    today = timezone.now().date()
    yesterday = today - timedelta(days=1)
    
    # Получаем все активные ссылки
    active_urls = ShortenedURL.objects.filter(is_active=True)
    
    for url in active_urls:
        # Считаем клики за вчерашний день
        yesterday_clicks = url.clicks.filter(
            clicked_at__date=yesterday
        ).count()
        
        if yesterday_clicks > 0:
            # Создаем или обновляем запись статистики
            DailyStats.objects.update_or_create(
                shortened_url=url,
                date=yesterday,
                defaults={
                    'clicks': yesterday_clicks,
                    'unique_visitors': url.clicks.filter(
                        clicked_at__date=yesterday
                    ).values('ip_address').distinct().count(),
                }
            )
    
    return True

def get_user_stats(user):
    """Получение статистики пользователя"""
    user_urls = ShortenedURL.objects.filter(user=user)
    
    stats = {
        'total_urls': user_urls.count(),
        'total_clicks': user_urls.aggregate(total=models.Sum('click_count'))['total'] or 0,
        'active_urls': user_urls.filter(is_active=True, expires_at__gt=timezone.now()).count(),
        'expired_urls': user_urls.filter(expires_at__lt=timezone.now()).count(),
        'today_clicks': ClickStatistics.objects.filter(
            shortened_url__user=user,
            clicked_at__date=timezone.now().date()
        ).count(),
    }
    
    return stats

def create_test_data(user, count=10):
    """Создание тестовых данных для разработки"""
    from datetime import datetime, timedelta
    
    for i in range(count):
        short_code = generate_short_code()
        ShortenedURL.objects.create(
            original_url=f'https://example.com/test/{i}',
            short_code=short_code,
            title=f'Тестовая ссылка {i+1}',
            user=user,
            expires_at=timezone.now() + timedelta(days=random.randint(1, 365)),
            click_count=random.randint(0, 1000)
        )
    
    return f'Создано {count} тестовых ссылок'