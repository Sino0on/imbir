from django.core import mail
from django.db import IntegrityError, transaction
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from reviews.models import Review
from users.models import ClinicProfile, DoctorProfile, User


class ReviewUniquenessTests(APITestCase):
    url = '/api/reviews/'

    def setUp(self):
        self.patient = User.objects.create_user(
            email='reviewer@example.com', password='password123', role=User.Role.PATIENT,
        )
        self.doctor_user = User.objects.create_user(
            email='doctor@example.com', password='password123', role=User.Role.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(user=self.doctor_user, is_published=True)
        self.clinic_user = User.objects.create_user(
            email='clinic@example.com', password='password123', role=User.Role.CLINIC,
        )
        self.clinic = ClinicProfile.objects.create(
            user=self.clinic_user, name='Клиника', is_published=True,
        )
        self.client.force_authenticate(user=self.patient)

    def test_api_allows_only_one_review_per_doctor_and_clinic(self):
        doctor_payload = {
            'target_type': Review.TargetType.DOCTOR,
            'target_id': self.doctor_user.id,
            'rating': 5,
            'text': 'Спасибо',
        }
        clinic_payload = {
            'target_type': Review.TargetType.CLINIC,
            'target_id': self.clinic_user.id,
            'rating': 4,
            'text': 'Хорошая клиника',
        }

        self.assertEqual(self.client.post(self.url, doctor_payload, format='json').status_code, status.HTTP_201_CREATED)
        duplicate_doctor = self.client.post(self.url, doctor_payload, format='json')
        self.assertEqual(duplicate_doctor.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('уже оставили', str(duplicate_doctor.data))

        self.assertEqual(self.client.post(self.url, clinic_payload, format='json').status_code, status.HTTP_201_CREATED)
        duplicate_clinic = self.client.post(self.url, clinic_payload, format='json')
        self.assertEqual(duplicate_clinic.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('уже оставили', str(duplicate_clinic.data))

        self.assertEqual(Review.objects.filter(author=self.patient, doctor=self.doctor).count(), 1)
        self.assertEqual(Review.objects.filter(author=self.patient, clinic=self.clinic).count(), 1)

    def test_database_constraints_prevent_bypassing_the_api(self):
        Review.objects.create(
            author=self.patient,
            target_type=Review.TargetType.DOCTOR,
            doctor=self.doctor,
            rating=5,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Review.objects.create(
                    author=self.patient,
                    target_type=Review.TargetType.DOCTOR,
                    doctor=self.doctor,
                    rating=1,
                )


class ReviewAuthorRoleTests(APITestCase):
    """Врач и клиника не могут оценивать ни себя, ни других (N30)."""
    url = '/api/reviews/'

    def setUp(self):
        self.doctor_user = User.objects.create_user(
            email='doc-self@example.com', password='password123', role=User.Role.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(user=self.doctor_user, is_published=True)
        self.other_doctor_user = User.objects.create_user(
            email='doc-other@example.com', password='password123', role=User.Role.DOCTOR,
        )
        DoctorProfile.objects.create(user=self.other_doctor_user, is_published=True)
        self.clinic_user = User.objects.create_user(
            email='clinic-self@example.com', password='password123', role=User.Role.CLINIC,
        )
        self.clinic = ClinicProfile.objects.create(user=self.clinic_user, name='Клиника', is_published=True)

    def _post(self, user, target_type, target_id):
        self.client.force_authenticate(user=user)
        return self.client.post(self.url, {
            'target_type': target_type, 'target_id': target_id, 'rating': 5,
        }, format='json')

    def test_doctor_cannot_review_self(self):
        response = self._post(self.doctor_user, Review.TargetType.DOCTOR, self.doctor_user.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Review.objects.exists())
        self.doctor.refresh_from_db()
        self.assertEqual(self.doctor.reviews_count, 0)

    def test_doctor_cannot_review_competitor(self):
        response = self._post(self.doctor_user, Review.TargetType.DOCTOR, self.other_doctor_user.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('только пациенты', str(response.data))

    def test_clinic_cannot_review_self(self):
        response = self._post(self.clinic_user, Review.TargetType.CLINIC, self.clinic_user.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Review.objects.exists())

    def test_patient_cannot_review_own_leftover_doctor_profile(self):
        # Аккаунт сменил роль, а профиль врача остался опубликованным.
        self.doctor_user.role = User.Role.PATIENT
        self.doctor_user.save(update_fields=['role'])
        response = self._post(self.doctor_user, Review.TargetType.DOCTOR, self.doctor_user.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('самому себе', str(response.data))

    def test_patient_can_review_with_rating_only(self):
        patient = User.objects.create_user(
            email='patient-ok@example.com', password='password123', role=User.Role.PATIENT,
        )
        response = self._post(patient, Review.TargetType.DOCTOR, self.doctor_user.id)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', ADMINS=[])
class ReviewComplaintTests(APITestCase):
    """POST /api/reviews/{id}/complaint/ доводит жалобу до администратора (N29)."""

    def setUp(self):
        from references.models import SiteSettings

        self.patient = User.objects.create_user(
            email='author@example.com', password='password123', role=User.Role.PATIENT,
        )
        self.doctor_user = User.objects.create_user(
            email='doc-c@example.com', password='password123', role=User.Role.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(user=self.doctor_user, is_published=True)
        self.review = Review.objects.create(
            author=self.patient, target_type=Review.TargetType.DOCTOR,
            doctor=self.doctor, rating=1, text='Плохой врач',
        )
        site = SiteSettings.load()
        site.contact_email = 'admin@imbir.kg'
        site.save()
        self.url = f'/api/reviews/{self.review.id}/complaint/'

    def test_target_doctor_complaint_is_emailed_to_admin(self):
        self.client.force_authenticate(user=self.doctor_user)
        response = self.client.post(self.url, {
            'reason': 'Ложная информация', 'comment': 'Пациент у меня не был',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ['admin@imbir.kg'])
        self.assertIn(f'#{self.review.id}', message.subject)
        self.assertIn('Ложная информация', message.body)
        self.assertIn('Пациент у меня не был', message.body)
        self.assertIn('Плохой врач', message.body)

    def test_falls_back_to_superusers_without_contact_email(self):
        from references.models import SiteSettings

        site = SiteSettings.load()
        site.contact_email = ''
        site.save()
        User.objects.create_superuser(email='root@imbir.kg', password='password123')
        self.client.force_authenticate(user=self.doctor_user)
        response = self.client.post(self.url, {'reason': 'Спам или реклама'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(mail.outbox[0].to, ['root@imbir.kg'])

    def test_reason_is_required(self):
        self.client.force_authenticate(user=self.doctor_user)
        response = self.client.post(self.url, {'comment': 'без причины'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(len(mail.outbox), 0)

    def test_only_review_target_can_complain(self):
        stranger = User.objects.create_user(
            email='stranger@example.com', password='password123', role=User.Role.DOCTOR,
        )
        self.client.force_authenticate(user=stranger)
        response = self.client.post(self.url, {'reason': 'Спам или реклама'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(len(mail.outbox), 0)

    def test_anonymous_cannot_complain(self):
        response = self.client.post(self.url, {'reason': 'Спам или реклама'}, format='json')
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
        self.assertEqual(len(mail.outbox), 0)


class ReviewReplyEditTests(APITestCase):
    """Повторный POST /reply/ от клиники заменяет ответ (N32)."""

    def test_clinic_can_replace_reply(self):
        patient = User.objects.create_user(
            email='p-reply@example.com', password='password123', role=User.Role.PATIENT,
        )
        clinic_user = User.objects.create_user(
            email='c-reply@example.com', password='password123', role=User.Role.CLINIC,
        )
        clinic = ClinicProfile.objects.create(user=clinic_user, name='Клиника', is_published=True)
        review = Review.objects.create(
            author=patient, target_type=Review.TargetType.CLINIC, clinic=clinic, rating=4,
        )
        self.client.force_authenticate(user=clinic_user)
        url = f'/api/reviews/{review.id}/reply/'
        self.assertEqual(self.client.post(url, {'text': 'Спсибо'}, format='json').status_code, 200)
        response = self.client.post(url, {'text': 'Спасибо!'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['reply']['text'], 'Спасибо!')
        review.refresh_from_db()
        self.assertEqual(review.reply_text, 'Спасибо!')
