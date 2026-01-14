def user_profile_processor(request):
    """Добавляет профиль пользователя в контекст всех шаблонов"""
    context = {}
    if request.user.is_authenticated:
        from .models import UserProfile
        try:
            profile = UserProfile.objects.get(user=request.user)
            context['user_profile'] = profile
        except UserProfile.DoesNotExist:
            profile = UserProfile.objects.create(user=request.user)
            context['user_profile'] = profile
    return context