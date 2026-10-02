from django.core.management.base import BaseCommand
from django.db import transaction

from references.models import Specialization


# Reuse existing IDs and naming variants so doctors and catalogue filters keep
# pointing to the same specialization instead of splitting across duplicates.
REGISTRATION_SPECIALIZATIONS = (
    ('Кардиология', ('Кардиолог',)),
    ('Эндокринология', ('Эндокринолог', 'врач эндокринолог')),
    ('Ревматология', ('Ревматолог', 'Диагностика и лечение ревматических заболеваний')),
    ('Травматология и ортопедия', ('Ортопед', 'Ортопедия')),
    ('Гастроэнтерология', ('Гастроэнтеролог',)),
    ('Флеболог', ('Флебология',)),
    ('Урология', ('Уролог',)),
    ('Маммология', ('Маммолог',)),
    ('Фиброскан', ()),
    ('Оториноларингология', ('Лор', 'Отоларингология')),
    ('Офтальмология', ('Окулист', 'Офтальмолог', 'врач-офтальмолог высшей квалификационной категории')),
    ('Хирургия', ('Хирург',)),
    ('Дерматология', ('Дерматолог',)),
    ('Гепатолог', ('Гепатология',)),
)


class Command(BaseCommand):
    help = 'Добавить недостающие специализации для регистрации, сохраняя существующие ID.'

    @transaction.atomic
    def handle(self, *args, **options):
        created = 0
        existing_names = {
            name.strip().casefold()
            for name in Specialization.objects.values_list('name', flat=True)
        }
        for name, aliases in REGISTRATION_SPECIALIZATIONS:
            if not any(candidate.strip().casefold() in existing_names for candidate in (name, *aliases)):
                Specialization.objects.create(name=name)
                existing_names.add(name.casefold())
                created += 1
        self.stdout.write(self.style.SUCCESS(f'Добавлено: {created}; направлений проверено: {len(REGISTRATION_SPECIALIZATIONS)}.'))
