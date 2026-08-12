"""
Наполняет справочник статусов аккаунта (AccountStatus) моковыми данными.

Идемпотентна: повторный запуск обновляет описание/процент по имени, а не
плодит дубли.
Запуск:  python manage.py seed_account_statuses
"""
from django.core.management.base import BaseCommand

from references.models import AccountStatus

STATUSES = [
    {
        'name': 'Витамин С',
        'description': (
            'Ваши отзывы действуют на врачей как ударная доза витамина С! '
            'Вы замечаете светлые стороны, дарите надежду другим пациентам '
            'и помогаете клинике расцветать. Спасибо за ваш позитивный заряд!'
        ),
        'percent': 90,
    },
    {
        'name': 'Здоровый Пульс',
        'description': (
            'Вы — индикатор того, что всё идет правильно. Ваши отзывы ритмичны, '
            'четки и всегда на позитивной волне. Вы помогаете нам держать руку '
            'на пульсе качественного сервиса.'
        ),
        'percent': 75,
    },
    {
        'name': 'Взвешенная Доза',
        'description': (
            'Золотой стандарт объективности. Вы видите и плюсы, и минусы, '
            'соблюдая идеальный баланс. Вашему мнению доверяют, потому что оно '
            'лишено лишних эмоций и полно здравого смысла.'
        ),
        'percent': 55,
    },
    {
        'name': 'Строгий Диагност',
        'description': (
            'Видит суть сквозь формальности. Оценивает не обертку, а '
            'квалификацию и доказательный подход. Ваше мнение — это высшая '
            'аттестация для медицинского персонала.'
        ),
        'percent': 35,
    },
    {
        'name': 'Острый Скальпель',
        'description': (
            'Вы не боитесь резать правду-матку! Ваши отзывы помогают нам '
            'проводить "хирургические операции" над нашими ошибками. Благодаря '
            'вашей прямоте мы отсекаем всё лишнее и становимся лучше.'
        ),
        'percent': 10,
    },
]


class Command(BaseCommand):
    help = 'Наполняет справочник статусов аккаунта (AccountStatus) моковыми данными'

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0

        for entry in STATUSES:
            obj, created = AccountStatus.objects.update_or_create(
                name=entry['name'],
                defaults={
                    'description': entry['description'],
                    'percent': entry['percent'],
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'Готово. Создано: {created_count}, обновлено: {updated_count}, '
            f'всего в справочнике: {AccountStatus.objects.count()}.'
        ))
