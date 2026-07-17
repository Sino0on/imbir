"""
Подбор рекомендаций по тегам, которые вернул ИИ.

query_recommendations() — по именам тегов и типам сущностей находит id, ранжируя
по числу совпавших тегов (затем по рейтингу). serialize_recommendations() —
по сохранённым id пересобирает карточки из свежих данных.
"""
from django.db.models import Count, Q

ENTITY_TYPES = ('doctors', 'clinics', 'services')
DEFAULT_LIMIT = 3


def _resolve_tag_ids(tag_names):
    # Регистронезависимое сопоставление в Python: iexact на SQLite не работает
    # с кириллицей, а словарь тегов небольшой.
    from references.models import Tag
    if not tag_names:
        return []
    wanted = {str(n).strip().casefold() for n in tag_names if n and str(n).strip()}
    if not wanted:
        return []
    return [
        pk for pk, name in Tag.objects.values_list('id', 'name')
        if name.casefold() in wanted
    ]


def query_recommendations(tag_names, entity_types, limit=DEFAULT_LIMIT):
    """Возвращает {'doctors': [ids], 'clinics': [ids], 'services': [ids]} по совпадению тегов."""
    from users.models import DoctorProfile, ClinicProfile
    from services.models import Service

    result = {'doctors': [], 'clinics': [], 'services': []}
    tag_ids = _resolve_tag_ids(tag_names)
    if not tag_ids:
        return result

    wanted = set(entity_types or ENTITY_TYPES)

    def ranked(qs):
        return list(
            qs.filter(tags__in=tag_ids)
            .annotate(match_count=Count('tags', filter=Q(tags__in=tag_ids), distinct=True))
            .order_by('-match_count', '-rating')
            .values_list('pk', flat=True)
            .distinct()[:limit]
        )

    if 'doctors' in wanted:
        result['doctors'] = ranked(
            DoctorProfile.objects.filter(is_published=True, user__is_active=True)
        )
    if 'clinics' in wanted:
        result['clinics'] = ranked(
            ClinicProfile.objects.filter(is_published=True, user__is_active=True)
        )
    if 'services' in wanted:
        # у услуги нет собственного rating — ранжируем по совпадению и id
        result['services'] = list(
            Service.objects.filter(is_active=True, tags__in=tag_ids)
            .annotate(match_count=Count('tags', filter=Q(tags__in=tag_ids), distinct=True))
            .order_by('-match_count', '-id')
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
