from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from .models import ShortenedURL, UserProfile

class URLShortenForm(forms.ModelForm):
    custom_code = forms.CharField(
        max_length=20,
        required=False,
        label='Свой короткий код',
        help_text='Оставьте пустым для автоматической генерации'
    )
    
    expiry_days = forms.IntegerField(
        min_value=1,
        max_value=365,
        initial=30,
        label='Срок действия (дней)',
        help_text='Через сколько дней ссылка перестанет работать'
    )
    
    class Meta:
        model = ShortenedURL
        fields = ['original_url', 'title', 'description', 'tags', 'is_private', 'password']
        widgets = {
            'original_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://example.com/very-long-url-here',
                'autofocus': True
            }),
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Название ссылки (необязательно)'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Описание ссылки (необязательно)'
            }),
            'tags': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'тег1, тег2, тег3'
            }),
            'password': forms.PasswordInput(attrs={
                'class': 'form-control',
                'placeholder': 'Пароль для доступа к ссылке'
            }),
        }
        labels = {
            'original_url': 'Длинная ссылка',
            'is_private': 'Сделать приватной',
            'password': 'Пароль (если приватная)',
        }
    
    def clean_custom_code(self):
        custom_code = self.cleaned_data.get('custom_code')
        if custom_code:
            # Проверяем допустимые символы
            if not custom_code.isalnum():
                raise forms.ValidationError('Код может содержать только буквы и цифры')
            
            # Проверяем уникальность
            if ShortenedURL.objects.filter(short_code=custom_code).exists():
                raise forms.ValidationError('Этот код уже занят. Попробуйте другой.')
        return custom_code
    
    def save(self, commit=True, user=None):
        instance = super().save(commit=False)
        
        if user:
            instance.user = user
        
        # Устанавливаем короткий код
        custom_code = self.cleaned_data.get('custom_code')
        if custom_code:
            instance.short_code = custom_code
        
        # Устанавливаем срок истечения
        expiry_days = self.cleaned_data.get('expiry_days', 30)
        instance.expires_at = timezone.now() + timedelta(days=expiry_days)
        
        if commit:
            instance.save()
        
        return instance


class AdvancedURLShortenForm(URLShortenForm):
    """Расширенная форма с дополнительными настройками"""
    expiry_date = forms.DateTimeField(
        required=False,
        label='Конкретная дата истечения',
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
        help_text='Или укажите конкретную дату'
    )
    
    class Meta(URLShortenForm.Meta):
        fields = URLShortenForm.Meta.fields + ['is_private', 'password']


class UserRegisterForm(UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={
        'class': 'form-control',
        'placeholder': 'example@mail.com'
    }))
    
    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Имя пользователя'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs.update({'class': 'form-control'})
        self.fields['password2'].widget.attrs.update({'class': 'form-control'})
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        
        if commit:
            user.save()
            # Создаем профиль пользователя
            UserProfile.objects.create(user=user)
        
        return user


class UserLoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={
        'class': 'form-control',
        'placeholder': 'Имя пользователя или email'
    }))
    password = forms.CharField(widget=forms.PasswordInput(attrs={
        'class': 'form-control',
        'placeholder': 'Пароль'
    }))


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['website', 'default_link_expiry_days', 'show_advanced_options']  # Убраны 'bio' и 'theme'
        
    widgets = {
        'website': forms.URLInput(attrs={
            'class': 'form-control',
            'placeholder': 'https://your-website.com'
        }),
        'default_link_expiry_days': forms.NumberInput(attrs={
            'class': 'form-control'
        }),
    }


class StatsFilterForm(forms.Form):
    PERIOD_CHOICES = [
        ('today', 'Сегодня'),
        ('yesterday', 'Вчера'),
        ('week', 'Неделя'),
        ('month', 'Месяц'),
        ('year', 'Год'),
        ('all', 'Все время'),
        ('custom', 'Произвольный период'),
    ]
    
    period = forms.ChoiceField(
        choices=PERIOD_CHOICES,
        initial='week',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control',
            'placeholder': 'Начальная дата'
        })
    )
    
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control',
            'placeholder': 'Конечная дата'
        })
    )
    
    group_by = forms.ChoiceField(
        choices=[
            ('day', 'По дням'),
            ('week', 'По неделям'),
            ('month', 'По месяцам'),
        ],
        initial='day',
        widget=forms.Select(attrs={'class': 'form-select'})
    )