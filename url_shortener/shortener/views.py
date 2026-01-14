from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse, Http404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout, authenticate
from django.contrib import messages
from .models import ShortenedURL, ClickStatistics, UserProfile
from django.utils import timezone
from django.db.models import Count, Q, F, Sum
from django.db import transaction
from django.core.paginator import Paginator
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.conf import settings
from django_user_agents.utils import get_user_agent
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json

from datetime import datetime, timedelta
import json
try:
    import qrcode
    from io import BytesIO
    from django.core.files.base import ContentFile
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False
import uuid

from .models import ShortenedURL, ClickStatistics, DailyStats, UserProfile
from .forms import (
    URLShortenForm, AdvancedURLShortenForm, 
    UserRegisterForm, UserLoginForm, UserProfileForm,
    StatsFilterForm
)

def get_user_theme(request):
    """Получение темы пользователя"""
    if request.user.is_authenticated:
        try:
            profile = UserProfile.objects.get(user=request.user)
            if profile.theme == 'auto':
                # Проверяем системные настройки
                if 'dark' in request.META.get('HTTP_SEC_CH_UA_MODE', ''):
                    return 'dark'
                return 'light'
            return profile.theme
        except UserProfile.DoesNotExist:
            pass
    
    # По умолчанию светлая тема
    return 'light'

# Вспомогательные функции
def get_client_ip(request):
    """Получение IP адреса клиента"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def parse_user_agent(user_agent_string):
    """Парсинг User-Agent"""
    user_agent = get_user_agent(request=None, user_agent_string=user_agent_string)
    
    device_type = 'other'
    if user_agent.is_mobile:
        device_type = 'mobile'
    elif user_agent.is_tablet:
        device_type = 'tablet'
    elif user_agent.is_pc:
        device_type = 'desktop'
    elif user_agent.is_bot:
        device_type = 'bot'
    
    browser = 'other'
    if 'chrome' in user_agent_string.lower():
        browser = 'chrome'
    elif 'firefox' in user_agent_string.lower():
        browser = 'firefox'
    elif 'safari' in user_agent_string.lower() and 'chrome' not in user_agent_string.lower():
        browser = 'safari'
    elif 'edge' in user_agent_string.lower():
        browser = 'edge'
    elif 'opera' in user_agent_string.lower():
        browser = 'opera'
    
    return {
        'device_type': device_type,
        'browser': browser,
        'os': str(user_agent.os),
        'is_bot': user_agent.is_bot,
    }

# Основные представления
def home(request):
    """Главная страница"""
    context = {
        'theme': get_user_theme(request)
    }
    
    if request.method == 'POST':
        if request.user.is_authenticated and hasattr(request.user, 'profile') and request.user.profile.show_advanced_options:
            form = AdvancedURLShortenForm(request.POST)
        else:
            form = URLShortenForm(request.POST)
        
        if form.is_valid():
            shortened_url = form.save(user=request.user if request.user.is_authenticated else None)
            
            # Генерация QR кода (если доступна)
            if QRCODE_AVAILABLE:
                try:
                    qr = qrcode.make(shortened_url.get_short_url(request))
                    buffer = BytesIO()
                    qr.save(buffer, format='PNG')
                    
                    shortened_url.qr_code.save(
                        f'qr_{shortened_url.short_code}.png',
                        ContentFile(buffer.getvalue()),
                        save=True
                    )
                except Exception as e:
                    print(f"Ошибка генерации QR кода: {e}")
            
            context['shortened_url'] = shortened_url
            context['full_short_url'] = shortened_url.get_short_url(request)
            
            messages.success(request, 'Ссылка успешно создана!')
    
    else:
        if request.user.is_authenticated and hasattr(request.user, 'profile') and request.user.profile.show_advanced_options:
            form = AdvancedURLShortenForm()
        else:
            form = URLShortenForm()
    
    # Показываем последние публичные ссылки
    public_urls = ShortenedURL.objects.filter(
        is_private=False, 
        is_active=True,
        expires_at__gt=timezone.now()
    ).order_by('-created_at')[:10]
    
    context['form'] = form
    context['public_urls'] = public_urls
    
    return render(request, 'shortener/home.html', context)


def redirect_to_original(request, short_code):
    """Перенаправление по короткой ссылке"""
    shortened_url = get_object_or_404(
        ShortenedURL, 
        short_code=short_code,
        is_active=True
    )
    
    # Проверка срока действия
    if shortened_url.is_expired():
        return render(request, 'shortener/expired.html', {'url': shortened_url})
    
    # Проверка пароля для приватных ссылок
    if shortened_url.is_private and shortened_url.password:
        if request.method == 'POST':
            password = request.POST.get('password', '')
            if password == shortened_url.password:
                request.session[f'url_{shortened_url.id}_accessed'] = True
            else:
                messages.error(request, 'Неверный пароль')
                return render(request, 'shortener/password_protected.html', {'url': shortened_url})
        elif not request.session.get(f'url_{shortened_url.id}_accessed'):
            return render(request, 'shortener/password_protected.html', {'url': shortened_url})
    
    # Получаем информацию о клиенте
    ip_address = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    referer = request.META.get('HTTP_REFERER', '')
    
    # Парсим User-Agent
    ua_info = parse_user_agent(user_agent)
    
    # Создаем запись о клике
    with transaction.atomic():
        # Обновляем основную статистику
        shortened_url.increment_click_count()
        
        # Создаем детальную запись
        ClickStatistics.objects.create(
            shortened_url=shortened_url,
            ip_address=ip_address,
            user_agent=user_agent,
            referer=referer,
            device_type=ua_info['device_type'],
            browser=ua_info['browser'],
            operating_system=ua_info['os'],
            is_bot=ua_info['is_bot'],
            session_id=request.session.session_key or str(uuid.uuid4())[:8]
        )
        
        # Обновляем ежедневную статистику
        today = timezone.now().date()
        daily_stats, created = DailyStats.objects.get_or_create(
            shortened_url=shortened_url,
            date=today,
            defaults={'clicks': 1}
        )
        
        if not created:
            daily_stats.clicks = F('clicks') + 1
            daily_stats.save()
    
    # Перенаправляем на оригинальный URL
    return redirect(shortened_url.original_url)


@login_required
def dashboard(request):
    user_urls = ShortenedURL.objects.filter(user=request.user).order_by('-created_at')
    
    # Отладочный вывод в консоль
    print(f"=== DASHBOARD DEBUG ===")
    print(f"Пользователь: {request.user} (id: {request.user.id})")
    print(f"Найдено ссылок: {user_urls.count()}")
    if user_urls.exists():
        for i, url in enumerate(user_urls[:5]):
            print(f"  {i+1}. {url.short_code} -> {url.original_url[:50]}")
    else:
        print("  Нет ссылок для этого пользователя")
    print(f"=======================")
    
    total_urls = user_urls.count()
    total_clicks = sum(url.click_count for url in user_urls)
    active_urls = user_urls.filter(is_active=True, expires_at__gt=timezone.now()).count()
    
    # Если параметр all=true, показываем все ссылки
    if request.GET.get('all') == 'true':
        context_user_urls = user_urls
    else:
        context_user_urls = user_urls[:20]
    
    context = {
        'user_urls': context_user_urls,
        'total_urls': total_urls,
        'total_clicks': total_clicks,
        'active_urls': active_urls,
    }
    return render(request, 'shortener/dashboard.html', context)


@login_required
def url_detail(request, short_code):
    """Детальная информация о ссылке"""
    shortened_url = get_object_or_404(
        ShortenedURL, 
        short_code=short_code,
        user=request.user
    )
    
    # Форма фильтрации статистики
    filter_form = StatsFilterForm(request.GET or None)
    
    # Базовый queryset для кликов
    clicks_qs = ClickStatistics.objects.filter(shortened_url=shortened_url)
    
    # Применяем фильтры
    period = request.GET.get('period', 'week')
    
    if period == 'today':
        clicks_qs = clicks_qs.filter(clicked_at__date=timezone.now().date())
    elif period == 'yesterday':
        yesterday = timezone.now().date() - timedelta(days=1)
        clicks_qs = clicks_qs.filter(clicked_at__date=yesterday)
    elif period == 'week':
        week_ago = timezone.now() - timedelta(days=7)
        clicks_qs = clicks_qs.filter(clicked_at__gte=week_ago)
    elif period == 'month':
        month_ago = timezone.now() - timedelta(days=30)
        clicks_qs = clicks_qs.filter(clicked_at__gte=month_ago)
    elif period == 'year':
        year_ago = timezone.now() - timedelta(days=365)
        clicks_qs = clicks_qs.filter(clicked_at__gte=year_ago)
    elif period == 'custom':
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        if start_date and end_date:
            clicks_qs = clicks_qs.filter(
                clicked_at__date__gte=start_date,
                clicked_at__date__lte=end_date
            )
    
    # Статистика по времени суток
    hourly_stats = []
    for hour in range(24):
        count = clicks_qs.filter(clicked_at__hour=hour).count()
        hourly_stats.append({'hour': hour, 'count': count})
    
    # Статистика по дням недели
    days_of_week = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    daily_stats = []
    for i, day in enumerate(days_of_week):
        count = clicks_qs.filter(clicked_at__week_day=i+2).count()  # Django неделя начинается с воскресенья (1)
        daily_stats.append({'day': day, 'count': count})
    
    # Топ стран
    top_countries = clicks_qs.exclude(country='').values('country').annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    
    # Распределение по устройствам и браузерам
    device_stats = clicks_qs.values('device_type').annotate(
        count=Count('id'),
        percentage=Count('id') * 100.0 / clicks_qs.count()
    ).order_by('-count')
    
    browser_stats = clicks_qs.values('browser').annotate(
        count=Count('id'),
        percentage=Count('id') * 100.0 / clicks_qs.count()
    ).order_by('-count')
    
    # Последние клики
    recent_clicks = clicks_qs.order_by('-clicked_at')[:20]
    
    # Ежедневная статистика
    daily_stats_qs = DailyStats.objects.filter(
        shortened_url=shortened_url
    ).order_by('-date')[:30]
    
    # Подготавливаем данные для графиков
    chart_data = {
        'labels': [stat.date.strftime('%d.%m') for stat in daily_stats_qs][::-1],
        'clicks': [stat.clicks for stat in daily_stats_qs][::-1],
    }
    
    context = {
        'url': shortened_url,
        'filter_form': filter_form,
        'recent_clicks': recent_clicks,
        'hourly_stats': hourly_stats,
        'daily_stats': daily_stats,
        'top_countries': top_countries,
        'device_stats': device_stats,
        'browser_stats': browser_stats,
        'daily_stats_qs': daily_stats_qs,
        'chart_data': json.dumps(chart_data),
        'total_filtered_clicks': clicks_qs.count(),
    }
    
    return render(request, 'shortener/url_detail.html', context)


@login_required
def edit_url(request, short_code):
    """Редактирование ссылки"""
    shortened_url = get_object_or_404(
        ShortenedURL, 
        short_code=short_code,
        user=request.user
    )
    
    if request.method == 'POST':
        form = URLShortenForm(request.POST, instance=shortened_url)
        if form.is_valid():
            form.save()
            messages.success(request, 'Ссылка успешно обновлена!')
            return redirect('url_detail', short_code=shortened_url.short_code)
    else:
        form = URLShortenForm(instance=shortened_url)
    
    return render(request, 'shortener/edit_url.html', {
        'form': form,
        'url': shortened_url
    })


@login_required
@require_POST
def delete_url(request, short_code):
    """Удаление ссылки"""
    shortened_url = get_object_or_404(
        ShortenedURL, 
        short_code=short_code,
        user=request.user
    )
    
    shortened_url.delete()
    messages.success(request, 'Ссылка успешно удалена!')
    return redirect('dashboard')


@login_required
@require_POST
def toggle_url_status(request, short_code):
    """Активация/деактивация ссылки"""
    shortened_url = get_object_or_404(
        ShortenedURL, 
        short_code=short_code,
        user=request.user
    )
    
    shortened_url.is_active = not shortened_url.is_active
    shortened_url.save()
    
    action = 'активирована' if shortened_url.is_active else 'деактивирована'
    messages.success(request, f'Ссылка успешно {action}!')
    
    return redirect('url_detail', short_code=shortened_url.short_code)


def user_register(request):
    """Регистрация пользователя"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Добро пожаловать, {user.username}!')
            return redirect('dashboard')
    else:
        form = UserRegisterForm()
    
    return render(request, 'shortener/register.html', {'form': form})


def user_login(request):
    """Авторизация пользователя"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = UserLoginForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f'С возвращением, {user.username}!')
            
            # Перенаправляем на следующую страницу или dashboard
            next_page = request.GET.get('next', 'dashboard')
            return redirect(next_page)
    else:
        form = UserLoginForm()
    
    return render(request, 'shortener/login.html', {'form': form})


def user_logout(request):
    """Выход из системы"""
    logout(request)
    messages.info(request, 'Вы успешно вышли из системы.')
    return redirect('home')


@login_required
def user_profile(request):
    """Профиль пользователя"""
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Профиль успешно обновлен!')
            return redirect('user_profile')
    else:
        form = UserProfileForm(instance=profile)
    
    return render(request, 'shortener/profile.html', {'form': form})


@login_required
def generate_api_key(request):
    """Генерация нового API ключа"""
    profile = request.user.profile
    profile.api_key = uuid.uuid4().hex
    profile.save()
    
    messages.success(request, 'Новый API ключ успешно сгенерирован!')
    return redirect('user_profile')


# API Views
@csrf_exempt
@require_POST
def api_shorten(request):
    """API для сокращения ссылок"""
    # Проверка API ключа
    api_key = request.headers.get('X-API-Key') or request.POST.get('api_key')
    
    if not api_key:
        return JsonResponse({'error': 'API ключ обязателен'}, status=401)
    
    try:
        profile = UserProfile.objects.get(api_key=api_key)
    except UserProfile.DoesNotExist:
        return JsonResponse({'error': 'Неверный API ключ'}, status=401)
    
    # Проверка лимитов использования
    if profile.api_usage >= 1000:  # Пример лимита
        return JsonResponse({'error': 'Превышен лимит использования API'}, status=429)
    
    # Обработка запроса
    original_url = request.POST.get('url') or json.loads(request.body).get('url')
    
    if not original_url:
        return JsonResponse({'error': 'URL обязателен'}, status=400)
    
    # Создание короткой ссылки
    custom_code = request.POST.get('custom_code') or json.loads(request.body).get('custom_code', '')
    
    shortened_url = ShortenedURL.objects.create(
        original_url=original_url,
        user=profile.user,
    )
    
    if custom_code:
        if ShortenedURL.objects.filter(short_code=custom_code).exists():
            return JsonResponse({'error': 'Код уже занят'}, status=400)
        shortened_url.short_code = custom_code
        shortened_url.save()
    
    # Увеличиваем счетчик использования API
    profile.api_usage = F('api_usage') + 1
    profile.save()
    
    return JsonResponse({
        'short_url': shortened_url.get_short_url(request),
        'short_code': shortened_url.short_code,
        'original_url': shortened_url.original_url,
        'expires_at': shortened_url.expires_at.isoformat() if shortened_url.expires_at else None,
    })


@require_GET
def api_stats(request, short_code):
    """API для получения статистики"""
    api_key = request.headers.get('X-API-Key')
    
    if not api_key:
        return JsonResponse({'error': 'API ключ обязателен'}, status=401)
    
    try:
        profile = UserProfile.objects.get(api_key=api_key)
    except UserProfile.DoesNotExist:
        return JsonResponse({'error': 'Неверный API ключ'}, status=401)
    
    # Проверяем, что ссылка принадлежит пользователю
    try:
        shortened_url = ShortenedURL.objects.get(
            short_code=short_code,
            user=profile.user
        )
    except ShortenedURL.DoesNotExist:
        return JsonResponse({'error': 'Ссылка не найдена'}, status=404)
    
    # Получаем статистику за последние 30 дней
    thirty_days_ago = timezone.now() - timedelta(days=30)
    daily_stats = DailyStats.objects.filter(
        shortened_url=shortened_url,
        date__gte=thirty_days_ago.date()
    ).order_by('date')
    
    stats_data = []
    for stat in daily_stats:
        stats_data.append({
            'date': stat.date.isoformat(),
            'clicks': stat.clicks,
            'unique_visitors': stat.unique_visitors,
        })
    
    return JsonResponse({
        'short_code': shortened_url.short_code,
        'total_clicks': shortened_url.click_count,
        'created_at': shortened_url.created_at.isoformat(),
        'expires_at': shortened_url.expires_at.isoformat() if shortened_url.expires_at else None,
        'is_active': shortened_url.is_active,
        'daily_stats': stats_data,
    })

@csrf_exempt
@login_required
def update_theme(request):
    """API для обновления темы"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            theme = data.get('theme', 'light')
            
            if theme not in ['light', 'dark', 'auto']:
                return JsonResponse({'error': 'Неверная тема'}, status=400)
            
            profile, created = UserProfile.objects.get_or_create(user=request.user)
            profile.theme = theme
            profile.save()
            
            return JsonResponse({'success': True, 'theme': theme})
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Неверный JSON'}, status=400)
    
    return JsonResponse({'error': 'Метод не поддерживается'}, status=405)


def handler404(request, exception):
    """Обработчик 404 ошибки"""
    return render(request, 'shortener/404.html', status=404)


def handler500(request):
    """Обработчик 500 ошибки"""
    return render(request, 'shortener/500.html', status=500)

