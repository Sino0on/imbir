"""
Подбор рекомендаций по специализациям, которые вернул ИИ. Отдельного словаря
тегов больше нет — используется тот же справочник Specialization, что и при
регистрации врача/клиники (primary_specializations/narrow_specializations).

query_recommendations() — по именам специализаций и типам сущностей находит id,
ранжируя по числу совпадений (сначала основные специализации, потом
дополнительные, затем по рейтингу). serialize_recommendations() — по
сохранённым id пересобирает карточки из свежих данных.
"""
from django.db.models import Count, Q

ENTITY_TYPES = ('doctors', 'clinics', 'services')
DEFAULT_LIMIT = 3


def _resolve_specialization_ids(names):
    # Регистронезависимое сопоставление в Python: iexact на SQLite не работает
    # с кириллицей, а справочник специализаций небольшой.
    from references.models import Specialization
    if not names:
        return []
    wanted = {str(n).strip().casefold() for n in names if n and str(n).strip()}
    if not wanted:
        return []
    return [
        pk for pk, name in Specialization.objects.values_list('id', 'name')
        if name.casefold() in wanted
    ]


def _ranked_by_specializations(qs, spec_ids, limit):
    """Для DoctorProfile/ClinicProfile — у обоих есть primary/narrow_specializations и rating."""
    match_q = Q(primary_specializations__in=spec_ids) | Q(narrow_specializations__in=spec_ids)
    return list(
        qs.filter(match_q)
        .annotate(
            primary_matches=Count(
                'primary_specializations', filter=Q(primary_specializations__in=spec_ids), distinct=True,
            ),
            narrow_matches=Count(
                'narrow_specializations', filter=Q(narrow_specializations__in=spec_ids), distinct=True,
            ),
        )
        .order_by('-primary_matches', '-narrow_matches', '-rating')
        .values_list('pk', flat=True)
        .distinct()[:limit]
    )


def query_recommendations(specialization_names, entity_types, limit=DEFAULT_LIMIT):
    """Возвращает {'doctors': [ids], 'clinics': [ids], 'services': [ids]} по совпадению специализаций."""
    from users.models import DoctorProfile, ClinicProfile
    from services.models import Service

    result = {'doctors': [], 'clinics': [], 'services': []}
    spec_ids = _resolve_specialization_ids(specialization_names)
    if not spec_ids:
        return result

    wanted = set(entity_types or ENTITY_TYPES)

    if 'doctors' in wanted:
        result['doctors'] = _ranked_by_specializations(
            DoctorProfile.objects.filter(is_published=True, user__is_active=True),
            spec_ids, limit,
        )
    if 'clinics' in wanted:
        result['clinics'] = _ranked_by_specializations(
            ClinicProfile.objects.filter(is_published=True, user__is_active=True),
            spec_ids, limit,
        )
    if 'services' in wanted:
        # У услуги нет своих специализаций — сопоставляем через специализации
        # привязанных к ней врачей (Service.doctors уже существует).
        match_q = Q(doctors__primary_specializations__in=spec_ids) | Q(doctors__narrow_specializations__in=spec_ids)
        result['services'] = list(
            Service.objects.filter(is_active=True)
            .filter(match_q)
            .annotate(
                primary_matches=Count(
                    'doctors__primary_specializations',
                    filter=Q(doctors__primary_specializations__in=spec_ids), distinct=True,
                ),
            )
            .order_by('-primary_matches', '-id')
            .values_list('pk', flat=True)
            .distinct()[:limit]
        )
    return result


def serialize_recommendations(ids, request):
    """По {'doctors':[ids],...} собирает карточки. Пустой/битый вход → пустые списки."""
    from .serializers import RecoDoctorSerializer, RecoClinicSerializer, RecoServiceSerializer
    from users.models import DoctorProfile, ClinicProfile
    from services.models import Service

    ids = ids or {}
    ctx = {'request': request}
    out = {'doctors': [], 'clinics': [], 'services': []}

    doctor_ids = ids.get('doctors') or []
    clinic_ids = ids.get('clinics') or []
    service_ids = ids.get('services') or []

    if doctor_ids:
        qs = DoctorProfile.objects.filter(pk__in=doctor_ids).select_related('user')
        by_id = {d.pk: d for d in qs}
        ordered = [by_id[i] for i in doctor_ids if i in by_id]
        out['doctors'] = RecoDoctorSerializer(ordered, many=True, context=ctx).data

    if clinic_ids:
        qs = ClinicProfile.objects.filter(pk__in=clinic_ids).select_related('user')
        by_id = {c.pk: c for c in qs}
        ordered = [by_id[i] for i in clinic_ids if i in by_id]
        out['clinics'] = RecoClinicSerializer(ordered, many=True, context=ctx).data

    if service_ids:
        qs = Service.objects.filter(pk__in=service_ids).select_related('clinic')
        by_id = {s.pk: s for s in qs}
        ordered = [by_id[i] for i in service_ids if i in by_id]
        out['services'] = RecoServiceSerializer(ordered, many=True, context=ctx).data

    return out
