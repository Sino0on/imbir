from rest_framework import status
from rest_framework.test import APITestCase

from reviews.models import Review
from users.models import ClinicProfile, DoctorProfile, User


class MyReviewsTargetFilterTests(APITestCase):
    """GET /api/profile/reviews/?target_type=&target_id= — проверка «уже
    оставлял отзыв» не зависит от первой страницы из 20 (N83)."""
    url = '/api/profile/reviews/'

    def setUp(self):
        self.patient = User.objects.create_user(
            email='many-reviews@example.com', password='password123', role=User.Role.PATIENT,
        )
        self.doctors = []
        for i in range(25):
            doctor_user = User.objects.create_user(
                email=f'doc{i}@example.com', password='password123', role=User.Role.DOCTOR,
            )
            doctor = DoctorProfile.objects.create(user=doctor_user, is_published=True)
            Review.objects.create(
                author=self.patient, target_type=Review.TargetType.DOCTOR, doctor=doctor, rating=5,
            )
            self.doctors.append(doctor)
        clinic_user = User.objects.create_user(
            email='clinic-f@example.com', password='password123', role=User.Role.CLINIC,
        )
        self.clinic = ClinicProfile.objects.create(user=clinic_user, name='Клиника', is_published=True)
        self.client.force_authenticate(user=self.patient)

    def test_oldest_review_is_found_by_target(self):
        oldest = self.doctors[0]
        # Без фильтра первая страница его не содержит.
        first_page = self.client.get(self.url).data['data']
        self.assertEqual(len(first_page), 20)

        response = self.client.get(self.url, {'target_type': 'doctor', 'target_id': oldest.user_id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']), 1)
        self.assertEqual(response.data['data'][0]['target_id'], oldest.user_id)

    def test_no_review_on_target_returns_empty(self):
        response = self.client.get(self.url, {'target_type': 'clinic', 'target_id': self.clinic.user_id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data'], [])

    def test_other_patients_reviews_are_not_returned(self):
        other = User.objects.create_user(
            email='other-p@example.com', password='password123', role=User.Role.PATIENT,
        )
        self.client.force_authenticate(user=other)
        response = self.client.get(
            self.url, {'target_type': 'doctor', 'target_id': self.doctors[0].user_id},
        )
        self.assertEqual(response.data['data'], [])

    def test_invalid_target_id_returns_empty(self):
        response = self.client.get(self.url, {'target_type': 'doctor', 'target_id': 'abc'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data'], [])

    def test_without_params_returns_whole_list(self):
        response = self.client.get(self.url)
        self.assertEqual(response.data['pagination']['total'], 25)
