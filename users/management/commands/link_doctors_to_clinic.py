from django.core.management.base import BaseCommand
from users.models import DoctorProfile, ClinicProfile, DoctorClinicLink


class Command(BaseCommand):
    help = 'Привязывает всех врачей к указанной клинике (по user_id)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clinic-id', type=int, default=4,
            help='user_id клиники (по умолчанию 4)',
        )

    def handle(self, *args, **options):
        clinic_user_id = options['clinic_id']

        try:
            clinic = ClinicProfile.objects.get(id=clinic_user_id)
        except ClinicProfile.DoesNotExist:
            self.stderr.write(self.style.ERROR(
                f'Клиника с id={clinic_user_id} не найдена.'
            ))
            return

        doctors = DoctorProfile.objects.all()
        created_count = 0
        skipped_count = 0

        for doctor in doctors:
            _, created = DoctorClinicLink.objects.get_or_create(
                doctor=doctor,
                clinic=clinic,
                defaults={'is_active': True},
            )
            if created:
                created_count += 1
                self.stdout.write(f'  + {doctor.user.full_name}')
            else:
                skipped_count += 1

        # Обновляем счётчик doctors_count
        clinic.doctors_count = clinic.doctor_links.filter(is_active=True).count()
        clinic.save(update_fields=['doctors_count'])

        self.stdout.write(self.style.SUCCESS(
            f'\nГотово! Клиника: {clinic.name}\n'
            f'  Создано связей: {created_count}\n'
            f'  Уже существовали: {skipped_count}\n'
            f'  doctors_count: {clinic.doctors_count}'
        ))
