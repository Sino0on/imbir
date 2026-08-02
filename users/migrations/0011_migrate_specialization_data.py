"""
Переносит primary_specializations/narrow_specializations врачей и клиник
из свободных строк (JSONField) в ссылки на справочник Specialization.

Дубли форм ("Кардиолог"/"Кардиология", "ЛОР"/"Отоларинголог"/"ЛОР-врач")
и унаследованные латинские коды из старой версии формы регистрации
("cardiologist", "therapist", "neurologist" и т.п.) сводятся к одному
каноническому русскому названию через SYNONYMS. Остальные значения
дедуплицируются без учёта регистра (первое встреченное написание
становится каноническим). Профиль не остаётся без специализации даже
если все его значения были мусором — в этом случае они переносятся как есть.
"""
from django.db import migrations


# Профессиональная/отраслевая форма или унаследованный латинский код → канон.
# Согласовано с references/management/commands/seed_tags.py, но, в отличие
# от него, латинские коды НЕ считаются мусором — их когда-то писала старая
# версия формы регистрации, и врачи с ними должны находиться по фильтрам.
SYNONYMS = {
    'кардиолог': 'Кардиология', 'кардиология': 'Кардиология', 'cardiologist': 'Кардиология',
    'педиатр': 'Педиатрия', 'педиатрия': 'Педиатрия', 'pediatrician': 'Педиатрия',
    'терапевт': 'Терапия', 'терапия': 'Терапия', 'общая терапия': 'Терапия', 'therapist': 'Терапия',
    'хирург': 'Хирургия', 'хирургия': 'Хирургия', 'общий хирург': 'Хирургия', 'surgeon': 'Хирургия',
    'невролог': 'Неврология', 'неврология': 'Неврология', 'невропатолог': 'Неврология',
    'neurologist': 'Неврология',
    'дерматолог': 'Дерматология', 'дерматология': 'Дерматология', 'дерматовенеролог': 'Дерматология',
    'dermatologist': 'Дерматология',
    'гинеколог': 'Гинекология', 'гинекология': 'Гинекология', 'акушер-гинеколог': 'Гинекология',
    'gynecologist': 'Гинекология',
    'уролог': 'Урология', 'уролог специалист': 'Урология', 'урология': 'Урология',
    'urologist': 'Урология',
    'офтальмолог': 'Офтальмология', 'офтальмология': 'Офтальмология', 'окулист': 'Офтальмология',
    'ophthalmologist': 'Офтальмология',
    'лор': 'Оториноларингология', 'лор-врач': 'Оториноларингология', 'лор врач': 'Оториноларингология',
    'отоларинголог': 'Оториноларингология', 'отоларингология': 'Оториноларингология',
    'оториноларинголог': 'Оториноларингология', 'оториноларингология': 'Оториноларингология',
    'otolaryngologist': 'Оториноларингология', 'ent': 'Оториноларингология',
    'эндокринолог': 'Эндокринология', 'эндокринология': 'Эндокринология',
    'endocrinologist': 'Эндокринология',
    'гастроэнтеролог': 'Гастроэнтерология', 'гастроэнтерология': 'Гастроэнтерология',
    'gastroenterologist': 'Гастроэнтерология',
    'ортопед': 'Травматология и ортопедия', 'ортопедия': 'Травматология и ортопедия',
    'травматолог': 'Травматология и ортопедия', 'травматология': 'Травматология и ортопедия',
    'травматолог ортопед': 'Травматология и ортопедия',
    'orthopedist': 'Травматология и ортопедия', 'traumatologist': 'Травматология и ортопедия',
    'психиатр': 'Психиатрия', 'психиатрия': 'Психиатрия', 'psychiatrist': 'Психиатрия',
    'психолог': 'Психотерапия', 'психотерапевт': 'Психотерапия', 'психотерапия': 'Психотерапия',
    'psychologist': 'Психотерапия', 'psychotherapist': 'Психотерапия',
    'стоматолог': 'Стоматология', 'стоматология': 'Стоматология', 'dentist': 'Стоматология',
    'онколог': 'Онкология', 'онкология': 'Онкология', 'oncologist': 'Онкология',
    'аллерголог': 'Аллергология', 'аллергология': 'Аллергология', 'allergist': 'Аллергология',
    'пульмонолог': 'Пульмонология', 'пульмонология': 'Пульмонология', 'pulmonologist': 'Пульмонология',
    'нефролог': 'Нефрология', 'нефрология': 'Нефрология', 'nephrologist': 'Нефрология',
    'ревматолог': 'Ревматология', 'ревматология': 'Ревматология', 'rheumatologist': 'Ревматология',
    'маммолог': 'Маммология', 'маммология': 'Маммология',
    'андролог': 'Андрология', 'андролог- это врач': 'Андрология', 'андрология': 'Андрология',
    'проктолог': 'Проктология', 'проктология': 'Проктология',
    'сосудистый хирург': 'Сосудистая хирургия', 'флеболог': 'Сосудистая хирургия',
    'узи-специалист': 'УЗИ-диагностика', 'узи- специалист': 'УЗИ-диагностика',
    'узи специалист': 'УЗИ-диагностика', 'специалист узи': 'УЗИ-диагностика',
}

# Мусор, который не переносим как отдельную специализацию, если у профиля
# есть хотя бы одно осмысленное значение рядом.
JUNK = {'das', 'test', 'тест', 'string', 'qwe', 'asd', 'врач', 'doctor', ''}


def _canonical_map(raw_values):
    """casefold(значение) -> каноническое имя (или None для мусора)."""
    mapping = {}
    for raw in raw_values:
        value = (raw or '').strip()
        if not value:
            continue
        key = value.casefold()
        if key in mapping:
            continue
        if key in SYNONYMS:
            mapping[key] = SYNONYMS[key]
        elif key in JUNK:
            mapping[key] = None
        else:
            mapping[key] = value
    return mapping


def _resolve(raw_list, canon_map):
    """Каноникализирует список, сохраняя порядок и убирая дубли/мусор."""
    seen = []
    for raw in (raw_list or []):
        value = (raw or '').strip()
        if not value:
            continue
        name = canon_map.get(value.casefold())
        if name and name not in seen:
            seen.append(name)
    if not seen:
        # Не оставляем профиль совсем без специализации из-за мусора —
        # переносим исходные значения как есть (доступны для правки в админке).
        for raw in (raw_list or []):
            value = (raw or '').strip()
            if value and value not in seen:
                seen.append(value)
    return seen


def migrate_specializations(apps, schema_editor):
    DoctorProfile = apps.get_model('users', 'DoctorProfile')
    ClinicProfile = apps.get_model('users', 'ClinicProfile')
    Specialization = apps.get_model('references', 'Specialization')

    all_raw = []
    doctor_rows = list(DoctorProfile.objects.values_list('pk', 'primary_specializations', 'narrow_specializations'))
    clinic_rows = list(ClinicProfile.objects.values_list('pk', 'primary_specializations', 'narrow_specializations'))
    for _, primary, narrow in doctor_rows + clinic_rows:
        all_raw.extend(primary or [])
        all_raw.extend(narrow or [])

    canon_map = _canonical_map(all_raw)

    spec_cache = {}

    def get_specialization(name):
        if name not in spec_cache:
            spec, _ = Specialization.objects.get_or_create(name=name)
            spec_cache[name] = spec
        return spec_cache[name]

    for pk, primary, narrow in doctor_rows:
        doctor = DoctorProfile.objects.get(pk=pk)
        primary_names = _resolve(primary, canon_map)
        narrow_names = _resolve(narrow, canon_map)
        if primary_names:
            doctor.primary_specializations_new.set(get_specialization(n) for n in primary_names)
        if narrow_names:
            doctor.narrow_specializations_new.set(get_specialization(n) for n in narrow_names)

    for pk, primary, narrow in clinic_rows:
        clinic = ClinicProfile.objects.get(pk=pk)
        primary_names = _resolve(primary, canon_map)
        narrow_names = _resolve(narrow, canon_map)
        if primary_names:
            clinic.primary_specializations_new.set(get_specialization(n) for n in primary_names)
        if narrow_names:
            clinic.narrow_specializations_new.set(get_specialization(n) for n in narrow_names)


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0010_specialization_m2m_temp'),
    ]

    operations = [
        migrations.RunPython(migrate_specializations, reverse_code=migrations.RunPython.noop),
    ]
