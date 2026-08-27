from django.db import IntegrityError, transaction
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
