from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Tag(models.Model):
    """
    Единый канонический словарь тегов. Привязывается M2M к врачам, клиникам
    и услугам. Весь список тегов отдаётся ИИ-ассистенту, который по запросу
    гостя выбирает подходящие теги — по ним бэкенд находит рекомендации.
    """
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)

    class Meta:
        verbose_name = 'Тег'
        verbose_name_plural = 'Теги'
        ordering = ['name']

    def __str__(self):
        return self.name


class Specialization(models.Model):
    """
    Канонический справочник специализаций врачей и клиник. Заменяет свободный
    ввод: врач/клиника ссылаются на записи этого справочника (primary/narrow),
    а не хранят произвольную строку — правки дублей делаются через админку.
    """
    name = models.CharField(max_length=150, unique=True)
    photo = models.ImageField(upload_to='specializations/photos/', null=True, blank=True)

    class Meta:
        verbose_name = 'Специализация'
        verbose_name_plural = 'Специализации'
        ordering = ['name']

    def __str__(self):
        return self.name


class SiteSettings(models.Model):
    """
    Общесайтовые настройки (соцсети, контакты, юридические тексты) — то, что
    нужно для футера и подобных мест. Синглтон: всегда ровно одна запись,
    редактируется через админку без деплоя. Используйте SiteSettings.load().
    """
    facebook_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    twitter_url = models.URLField(blank=True, verbose_name='X (Twitter)')
    linkedin_url = models.URLField(blank=True)

    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    address = models.CharField(max_length=255, blank=True)

    terms_text = models.TextField(blank=True, verbose_name='Условия и положения')
    privacy_policy_text = models.TextField(blank=True, verbose_name='Политика конфиденциальности')

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Настройки сайта'
        verbose_name_plural = 'Настройки сайта'

    def __str__(self):
        return 'Настройки сайта'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def load(cls) -> 'SiteSettings':
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class AccountStatus(models.Model):
    """
    Статус аккаунта пользователя: активен, заблокирован, удалён и т.д.
    Используется для фильтрации пользователей в разных местах.
    """
    name = models.CharField(max_length=250, verbose_name='Название статуса')
    image = models.ImageField(upload_to='account_statuses/', null=True, blank=True, verbose_name='Изображение') 
    description = models.TextField(blank=True, null=True, verbose_name='Описание статуса')
    percent = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name='Процент качества профиля',
    )

    class Meta:
        verbose_name = 'Статус аккаунта'
        verbose_name_plural = 'Статусы аккаунтов'
        ordering = ['name']

    def __str__(self):
        return self.name