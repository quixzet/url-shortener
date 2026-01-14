from django.contrib import admin
from django.contrib.auth.models import User, Group
from django.contrib.auth.admin import UserAdmin
from .models import ShortenedURL, ClickStatistics, DailyStats, UserProfile

# Отмена регистрации стандартных моделей
admin.site.unregister(User)
admin.site.unregister(Group)

# Inline для профиля пользователя
class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Профиль'

# Кастомный UserAdmin
class CustomUserAdmin(UserAdmin):
    inlines = (UserProfileInline,)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'date_joined')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups')
    search_fields = ('username', 'first_name', 'last_name', 'email')

# Inline для кликов
class ClickStatisticsInline(admin.TabularInline):
    model = ClickStatistics
    extra = 0
    readonly_fields = ('clicked_at', 'ip_address', 'device_type', 'browser', 'country')
    fields = ('clicked_at', 'ip_address', 'device_type', 'browser', 'country')
    can_delete = False
    
    def has_add_permission(self, request, obj):
        return False

# Inline для ежедневной статистики
class DailyStatsInline(admin.TabularInline):
    model = DailyStats
    extra = 0
    readonly_fields = ('date', 'clicks', 'unique_visitors')
    fields = ('date', 'clicks', 'unique_visitors')
    can_delete = False
    
    def has_add_permission(self, request, obj):
        return False

# Админ для ShortenedURL
@admin.register(ShortenedURL)
class ShortenedURLAdmin(admin.ModelAdmin):
    list_display = ('short_code', 'original_url_truncated', 'user', 'click_count', 
                    'created_at', 'is_active', 'is_expired_display')
    list_filter = ('is_active', 'created_at', 'user', 'is_private')
    search_fields = ('short_code', 'original_url', 'title', 'user__username')
    readonly_fields = ('created_at', 'updated_at', 'last_clicked', 'click_count')
    fieldsets = (
        ('Основная информация', {
            'fields': ('original_url', 'short_code', 'title', 'description', 'tags')
        }),
        ('Владелец', {
            'fields': ('user',)
        }),
        ('Настройки', {
            'fields': ('is_active', 'is_private', 'password', 'expires_at')
        }),
        ('Статистика', {
            'fields': ('click_count', 'last_clicked', 'created_at', 'updated_at', 'qr_code')
        }),
    )
    inlines = [ClickStatisticsInline, DailyStatsInline]
    
    def original_url_truncated(self, obj):
        return obj.original_url[:50] + '...' if len(obj.original_url) > 50 else obj.original_url
    original_url_truncated.short_description = 'Оригинальный URL'
    
    def is_expired_display(self, obj):
        if obj.is_expired():
            return 'Да'
        return 'Нет'
    is_expired_display.short_description = 'Истекла'
    
    actions = ['activate_urls', 'deactivate_urls']
    
    def activate_urls(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} ссылок активировано.')
    activate_urls.short_description = "Активировать выбранные ссылки"
    
    def deactivate_urls(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} ссылок деактивировано.')
    deactivate_urls.short_description = "Деактивировать выбранные ссылки"

# Админ для ClickStatistics
@admin.register(ClickStatistics)
class ClickStatisticsAdmin(admin.ModelAdmin):
    list_display = ('shortened_url', 'clicked_at', 'ip_address', 'device_type', 
                    'browser', 'country', 'is_bot')
    list_filter = ('device_type', 'browser', 'is_bot', 'clicked_at', 'country')
    search_fields = ('shortened_url__short_code', 'ip_address', 'country', 'city')
    readonly_fields = ('clicked_at', 'ip_address', 'user_agent', 'referer', 
                      'country', 'city', 'device_type', 'browser', 'operating_system')
    date_hierarchy = 'clicked_at'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False

# Админ для DailyStats
@admin.register(DailyStats)
class DailyStatsAdmin(admin.ModelAdmin):
    list_display = ('shortened_url', 'date', 'clicks', 'unique_visitors')
    list_filter = ('date', 'shortened_url')
    search_fields = ('shortened_url__short_code',)
    readonly_fields = ('date', 'clicks', 'unique_visitors', 'desktop_clicks', 
                      'mobile_clicks', 'tablet_clicks', 'top_countries')
    date_hierarchy = 'date'
    
    def has_add_permission(self, request):
        return False

# Регистрируем кастомного UserAdmin
admin.site.register(User, CustomUserAdmin)

# Кастомный заголовок админки
admin.site.site_header = "URL Shortener Администрирование"
admin.site.site_title = "URL Shortener Админ"
admin.site.index_title = "Добро пожаловать в панель управления"