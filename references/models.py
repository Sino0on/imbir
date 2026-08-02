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
