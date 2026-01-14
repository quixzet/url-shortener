from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import random
import string
from datetime import timedelta

class ShortenedURL(models.Model):
    # Основные поля
    original_url = models.URLField(max_length=2000, verbose_name="Оригинальный URL")
    short_code = models.CharField(max_length=20, unique=True, verbose_name="Короткий код")
    title = models.CharField(max_length=200, blank=True, verbose_name="Название ссылки")
    description = models.TextField(blank=True, verbose_name="Описание")
    
    # Временные метки
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name="Истекает")
    
    # Статистика
    click_count = models.PositiveIntegerField(default=0, verbose_name="Кликов")
    last_clicked = models.DateTimeField(null=True, blank=True, verbose_name="Последний клик")
    
    # Владелец
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, 
                            verbose_name="Пользователь", related_name='shortened_urls')
    
    # Настройки
    is_active = models.BooleanField(default=True, verbose_name="Активна")
    password = models.CharField(max_length=100, blank=True, verbose_name="Пароль (опционально)")
    is_private = models.BooleanField(default=False, verbose_name="Приватная ссылка")
    
    # Метки/теги
    tags = models.CharField(max_length=200, blank=True, verbose_name="Теги (через запятую)")
    
    # QR код (будем хранить путь к изображению)
    qr_code = models.ImageField(upload_to='qr_codes/', null=True, blank=True, verbose_name="QR код")
    
    class Meta:
        verbose_name = "Сокращенная ссылка"
        verbose_name_plural = "Сокращенные ссылки"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['short_code']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['is_active', 'expires_at']),
        ]
    
    def __str__(self):
        return f"{self.short_code} -> {self.original_url[:50]}..."
    
    def save(self, *args, **kwargs):
        # Генерируем короткий код если его нет
        if not self.short_code:
            self.short_code = self.generate_short_code()
        
        # Устанавливаем срок истечения по умолчанию (30 дней)
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=30)
        
        super().save(*args, **kwargs)
    
    @staticmethod
    def generate_short_code(length=6):
        """Генерация случайного короткого кода"""
        chars = string.ascii_letters + string.digits
        while True:
            code = ''.join(random.choice(chars) for _ in range(length))
            if not ShortenedURL.objects.filter(short_code=code).exists():
                return code
    
    def increment_click_count(self):
        """Увеличивает счетчик кликов и обновляет время последнего клика"""
        self.click_count += 1
        self.last_clicked = timezone.now()
        self.save(update_fields=['click_count', 'last_clicked'])
    
    def is_expired(self):
        """Проверяет, истекла ли ссылка"""
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False
    
    def days_left(self):
        """Сколько дней осталось до истечения"""
        if self.expires_at:
            delta = self.expires_at - timezone.now()
            return max(0, delta.days)
        return None
    
    def get_short_url(self, request=None):
        """Получает полный короткий URL"""
        if request:
            return request.build_absolute_uri(f'/{self.short_code}')
        return f'/{self.short_code}'


class ClickStatistics(models.Model):
    """Детальная статистика по кликам"""
    DEVICE_TYPES = [
        ('desktop', 'Десктоп'),
        ('mobile', 'Мобильный'),
        ('tablet', 'Планшет'),
        ('bot', 'Бот'),
        ('other', 'Другое'),
    ]
    
    BROWSER_TYPES = [
        ('chrome', 'Chrome'),
        ('firefox', 'Firefox'),
        ('safari', 'Safari'),
        ('edge', 'Edge'),
        ('opera', 'Opera'),
        ('other', 'Другое'),
    ]
    
    shortened_url = models.ForeignKey(ShortenedURL, on_delete=models.CASCADE, 
                                     related_name='clicks', verbose_name="Ссылка")
    
    # Информация о клике
    clicked_at = models.DateTimeField(auto_now_add=True, verbose_name="Время клика")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP адрес")
    user_agent = models.TextField(blank=True, verbose_name="User Agent")
    referer = models.URLField(max_length=1000, blank=True, verbose_name="Реферер")
    
    # Геолокация
    country = models.CharField(max_length=100, blank=True, verbose_name="Страна")
    city = models.CharField(max_length=100, blank=True, verbose_name="Город")
    latitude = models.FloatField(null=True, blank=True, verbose_name="Широта")
    longitude = models.FloatField(null=True, blank=True, verbose_name="Долгота")
    
    # Информация об устройстве
    device_type = models.CharField(max_length=20, choices=DEVICE_TYPES, 
                                  default='other', verbose_name="Тип устройства")
    browser = models.CharField(max_length=20, choices=BROWSER_TYPES, 
                              default='other', verbose_name="Браузер")
    operating_system = models.CharField(max_length=100, blank=True, verbose_name="ОС")
    
    # Дополнительно
    is_bot = models.BooleanField(default=False, verbose_name="Бот")
    session_id = models.CharField(max_length=100, blank=True, verbose_name="ID сессии")
    
    class Meta:
        verbose_name = "Статистика клика"
        verbose_name_plural = "Статистика кликов"
        ordering = ['-clicked_at']
        indexes = [
            models.Index(fields=['shortened_url', 'clicked_at']),
            models.Index(fields=['country', 'city']),
            models.Index(fields=['device_type', 'browser']),
        ]
    
    def __str__(self):
        return f"Клик на {self.shortened_url.short_code} в {self.clicked_at}"


class DailyStats(models.Model):
    """Ежедневная статистика для быстрого анализа"""
    shortened_url = models.ForeignKey(ShortenedURL, on_delete=models.CASCADE, 
                                     related_name='daily_stats', verbose_name="Ссылка")
    date = models.DateField(verbose_name="Дата")
    
    # Количественные показатели
    clicks = models.PositiveIntegerField(default=0, verbose_name="Клики")
    unique_visitors = models.PositiveIntegerField(default=0, verbose_name="Уникальные посетители")
    
    # Распределение по устройствам
    desktop_clicks = models.PositiveIntegerField(default=0, verbose_name="Клики с десктопов")
    mobile_clicks = models.PositiveIntegerField(default=0, verbose_name="Клики с мобильных")
    tablet_clicks = models.PositiveIntegerField(default=0, verbose_name="Клики с планшетов")
    
    # География
    top_countries = models.JSONField(default=dict, verbose_name="Топ стран")
    
    class Meta:
        verbose_name = "Ежедневная статистика"
        verbose_name_plural = "Ежедневная статистика"
        unique_together = ['shortened_url', 'date']
        ordering = ['-date']
    
    def __str__(self):
        return f"Статистика {self.shortened_url.short_code} за {self.date}"


class UserProfile(models.Model):
    """Расширенный профиль пользователя"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    
    # Информация о пользователе
    bio = models.TextField(blank=True, verbose_name="О себе")
    website = models.URLField(blank=True, verbose_name="Вебсайт")
    
    # Настройки
    default_link_expiry_days = models.IntegerField(default=30, verbose_name="Срок действия ссылок по умолчанию")
    show_advanced_options = models.BooleanField(default=False, verbose_name="Показывать расширенные настройки")
    theme = models.CharField(max_length=20, default='light', choices=[
        ('light', 'Светлая'),
        ('dark', 'Темная'),
        ('auto', 'Авто')
    ], verbose_name="Тема")
    
    # Статистика пользователя
    total_clicks = models.PositiveIntegerField(default=0, verbose_name="Всего кликов")
    total_links = models.PositiveIntegerField(default=0, verbose_name="Всего ссылок")
    
    # API
    api_key = models.CharField(max_length=64, blank=True, verbose_name="API ключ")
    api_usage = models.PositiveIntegerField(default=0, verbose_name="Использование API")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Профиль пользователя"
        verbose_name_plural = "Профили пользователей"
    
    def __str__(self):
        return f"Профиль {self.user.username}"