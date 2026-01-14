from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from shortener import views

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Аутентификация (должны быть перед динамическими путями!)
    path('register/', views.user_register, name='register'),
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
    
    # Пользовательские маршруты
    path('dashboard/', views.dashboard, name='dashboard'),
    path('profile/', views.user_profile, name='user_profile'),
    path('profile/api-key/', views.generate_api_key, name='generate_api_key'),
    
    # API маршруты
    path('api/shorten/', views.api_shorten, name='api_shorten'),
    path('api/stats/<str:short_code>/', views.api_stats, name='api_stats'),
    
    # Основные маршруты
    path('', views.home, name='home'),
    path('shorten/', views.home, name='shorten_url'),
    
    # URL для перенаправления (должен быть ПОСЛЕДНИМ!)
    path('<str:short_code>/', views.redirect_to_original, name='redirect'),
    path('<str:short_code>/stats/', views.url_detail, name='url_detail'),
    path('<str:short_code>/edit/', views.edit_url, name='edit_url'),
    path('<str:short_code>/delete/', views.delete_url, name='delete_url'),
    path('<str:short_code>/toggle/', views.toggle_url_status, name='toggle_url_status'),


    path('api/update-theme/', views.update_theme, name='update_theme'),
    
]

# Обработчики ошибок
handler404 = 'shortener.views.handler404'
handler500 = 'shortener.views.handler500'

# Для обслуживания медиафайлов в режиме разработки
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)