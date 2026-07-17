"""
Наполняет словарь тегов и привязывает их к существующим врачам, клиникам и услугам.

Теги строятся из уже имеющихся specializations (врачи/клиники) и category (услуги).
Профессиональные и отраслевые формы («Кардиолог» / «Кардиология») сводятся к одному
канону через SYNONYMS, поэтому у врача и клиники получается общий тег для матчинга.

Идемпотентна: повторный запуск пересобирает привязки и не плодит дубли.
Запуск:  python manage.py seed_tags
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

# Профессиональная / отраслевая форма → канонический тег.
SYNONYMS = {
    'кардиолог': 'Кардиология',
    'кардиология': 'Кардиология',
    'педиатр': 'Педиатрия',
    'педиатрия': 'Педиатрия',
    'терапевт': 'Терапия',
    'терапия': 'Терапия',
    'общая терапия': 'Терапия',
    'хирург': 'Хирургия',
    'хирургия': 'Хирургия',
    'невролог': 'Неврология',
    'неврология': 'Неврология',
    'невропатолог': 'Неврология',
    'дерматолог': 'Дерматология',
    'дерматология': 'Дерматология',
    'дерматовенеролог': 'Дерматология',
    'гинеколог': 'Гинекология',
    'гинекология': 'Гинекология',
    'уролог': 'Урология',
    'урология': 'Урология',
    'офтальмолог': 'Офтальмология',
    'офтальмология': 'Офтальмология',
    'окулист': 'Офтальмология',
    'лор': 'Оториноларингология',
    'отоларинголог': 'Оториноларингология',
    'оториноларинголог': 'Оториноларингология',
    'оториноларингология': 'Оториноларингология',
    'эндокринолог': 'Эндокринология',
    'эндокринология': 'Эндокринология',
    'гастроэнтеролог': 'Гастроэнтерология',
    'гастроэнтерология': 'Гастроэнтерология',
    'ортопед': 'Травматология и ортопедия',
    'ортопедия': 'Травматология и ортопедия',
    'травматолог': 'Травматология и ортопедия',
    'травматология': 'Травматология и ортопедия',
    'психиатр': 'Психиатрия',
    'психиатрия': 'Психиатрия',
    'психолог': 'Психотерапия',
    'психотерапевт': 'Психотерапия',
    'психотерапия': 'Психотерапия',
    'стоматолог': 'Стоматология',
    'стоматология': 'Стоматология',
    'онколог': 'Онкология',
    'онкология': 'Онкология',
    'аллерголог': 'Аллергология',
    'аллергология': 'Аллергология',
    'пульмонолог': 'Пульмонология',
    'пульмонология': 'Пульмонология',
    'нефролог': 'Нефрология',
    'нефрология': 'Нефрология',
    'ревматолог': 'Ревматология',
    'ревматология': 'Ревматология',
}

# Тестовый мусор, который не должен попасть в теги.
JUNK = {'das', 'test', 'тест', 'therapist', 'string', 'qwe', 'asd', ''}

# Транслитерация для slug (SlugField не принимает кириллицу).
_TRANSLIT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'h', 'ц': 'c', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '',
    'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
}


def _translit(text):
    return ''.join(_TRANSLIT.get(ch, ch) for ch in text.lower())


def canonical(raw):
    """Приводит сырое значение к каноническому имени тега или None (мусор/пусто)."""
    if not raw:
        return None
    value = str(raw).strip()
    key = value.casefold()
    if key in JUNK:
        return None
    if key in SYNONYMS:
        return SYNONYMS[key]
    return value[0].upper() + value[1:]


class Command(BaseCommand):
    help = 'Строит словарь тегов из specializations/category и привязывает к сущностям.'

    @transaction.atomic
    def handle(self, *args, **options):
        from references.models import Tag
        from users.models import DoctorProfile, ClinicProfile
        from services.models import Service

        tag_cache = {}

        def unique_slug(base):
            base = base or 'tag'
            slug = base
            i = 2
            while Tag.objects.filter(slug=slug).exists():
                slug = f'{base}-{i}'
                i += 1
            return slug

        def get_tag(name):
            if name not in tag_cache:
                existing = Tag.objects.filter(name=name).first()
                if existing:
                    tag_cache[name] = existing
                else:
                    base = slugify(_translit(name)) or slugify(name, allow_unicode=True)
                    tag_cache[name] = Tag.objects.create(name=name, slug=unique_slug(base))
            return tag_cache[name]

        def tags_for(*raw_lists):
            names = set()
            for raw_list in raw_lists:
                for raw in (raw_list or []):
                    name = canonical(raw)
                    if name:
                        names.add(name)
                    if len(names) >= 10:  # разумный предел на сущность
                        break
            return [get_tag(n) for n in names]

        doc_count = clinic_count = svc_count = 0

        for doctor in DoctorProfile.objects.all():
            tags = tags_for(doctor.primary_specializations, doctor.narrow_specializations)
            if tags:
                doctor.tags.set(tags)
                doc_count += 1

        for clinic in ClinicProfile.objects.all():
            tags = tags_for(clinic.primary_specializations, clinic.narrow_specializations)
            if tags:
                clinic.tags.set(tags)
                clinic_count += 1

        for service in Service.objects.all():
            tags = tags_for([service.category])
            if tags:
                service.tags.set(tags)
                svc_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'Тегов в словаре: {Tag.objects.count()}. '
            f'Привязано: врачей {doc_count}, клиник {clinic_count}, услуг {svc_count}.'
        ))
