"""
Разово докидывает clinic/branch старым услугам врачей, созданным до фикса
DoctorServiceWriteSerializer (там clinic/branch не подставлялись вообще).

Трогает только услуги с clinic IS NULL, у которых есть хотя бы один врач.
Логика подстановки — та же, что и в самом сериализаторе:
  - у врача ровно одна активная привязка к клинике -> подставляем её клинику/филиал;
  - ни одной или несколько -> пропускаем и просто перечисляем в отчёте
    (для нескольких клиник заранее не угадать, к какой относится услуга).

Идемпотентна: повторный запуск не трогает уже проставленные услуги.
Запуск:  python manage.py backfill_service_clinic
         python manage.py backfill_service_clinic --dry-run
"""
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'Проставляет clinic/branch услугам врачей, созданным до фикса привязки.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Только показать, что было бы сделано, ничего не сохранять.',
        )

    def handle(self, *args, **options):
        from services.models import Service

        dry_run = options['dry_run']
        candidates = Service.objects.filter(clinic__isnull=True).prefetch_related('doctors')

        updated, skipped_none, skipped_multiple = [], [], []

        with transaction.atomic():
            for service in candidates:
                doctors = list(service.doctors.all())
                if not doctors:
                    continue

                # Услуга, созданная врачом, обычно привязана к одному врачу —
                # но на всякий случай берём объединение привязок всех врачей услуги.
                links = []
                for doctor in doctors:
                    links.extend(doctor.clinic_links.filter(is_active=True))

                distinct_clinics = {l.clinic_id for l in links}

                if not distinct_clinics:
                    skipped_none.append(service.id)
                    continue
                if len(distinct_clinics) > 1:
                    skipped_multiple.append(service.id)
                    continue

                link = links[0]
                service.clinic = link.clinic
                service.branch = link.branch
                updated.append(service.id)
                if not dry_run:
                    service.save(update_fields=['clinic', 'branch'])

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(
            f'{"[dry-run] " if dry_run else ""}Обновлено: {len(updated)} {updated}'
        ))
        self.stdout.write(f'Пропущено (у врача(ей) нет активной клиники): {len(skipped_none)} {skipped_none}')
        self.stdout.write(f'Пропущено (несколько клиник, не угадать какая): {len(skipped_multiple)} {skipped_multiple}')
