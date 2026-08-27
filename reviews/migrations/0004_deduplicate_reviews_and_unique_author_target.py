from django.db import migrations, models
from django.db.models import Avg, Count


def remove_duplicate_reviews(apps, schema_editor):
    Review = apps.get_model('reviews', 'Review')
    DoctorProfile = apps.get_model('users', 'DoctorProfile')
    ClinicProfile = apps.get_model('users', 'ClinicProfile')

    affected_doctor_ids = set()
    affected_clinic_ids = set()

    for field, affected_ids in (
        ('doctor', affected_doctor_ids),
        ('clinic', affected_clinic_ids),
    ):
        target_filter = {f'{field}_id__isnull': False}
        duplicate_groups = (
            Review.objects.filter(**target_filter)
            .values(f'{field}_id', 'author_id')
            .annotate(count=Count('id'))
            .filter(count__gt=1)
        )

        for group in duplicate_groups.iterator():
            target_id = group[f'{field}_id']
            duplicate_ids = list(
                Review.objects.filter(**{f'{field}_id': target_id, 'author_id': group['author_id']})
                .order_by('-created_at', '-id')
                .values_list('id', flat=True)
            )
            duplicate_reviews = Review.objects.filter(id__in=duplicate_ids[1:])
            affected_doctor_ids.update(
                duplicate_reviews.exclude(doctor_id__isnull=True).values_list(
                    'doctor_id', flat=True
                )
            )
            affected_clinic_ids.update(
                duplicate_reviews.exclude(clinic_id__isnull=True).values_list(
                    'clinic_id', flat=True
                )
            )
            duplicate_reviews.delete()
            affected_ids.add(target_id)

    for doctor_id in affected_doctor_ids:
        aggregate = Review.objects.filter(doctor_id=doctor_id).aggregate(
            average=Avg('rating'), count=Count('id')
        )
        DoctorProfile.objects.filter(pk=doctor_id).update(
            rating=round(aggregate['average'] or 0, 2),
            reviews_count=aggregate['count'],
        )

    for clinic_id in affected_clinic_ids:
        aggregate = Review.objects.filter(clinic_id=clinic_id).aggregate(
            average=Avg('rating'), count=Count('id')
        )
        ClinicProfile.objects.filter(pk=clinic_id).update(
            rating=round(aggregate['average'] or 0, 2),
            reviews_count=aggregate['count'],
        )


class Migration(migrations.Migration):
    dependencies = [
        ('reviews', '0003_review_reply_created_at_review_reply_text'),
        ('users', '0017_alter_user_phone'),
    ]

    operations = [
        migrations.RunPython(remove_duplicate_reviews, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='review',
            constraint=models.UniqueConstraint(
                fields=('author', 'doctor'),
                condition=models.Q(('doctor__isnull', False)),
                name='uniq_review_author_doctor',
            ),
        ),
        migrations.AddConstraint(
            model_name='review',
            constraint=models.UniqueConstraint(
                fields=('author', 'clinic'),
                condition=models.Q(('clinic__isnull', False)),
                name='uniq_review_author_clinic',
            ),
        ),
    ]
