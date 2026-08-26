from rest_framework import status
from rest_framework.test import APITestCase

from users.models import DoctorProfile, User


class DoctorOwnProfileTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='doctor-profile@example.com', password='password123',
            first_name='Алина', last_name='Садыкова', role=User.Role.DOCTOR,
        )
        self.profile = DoctorProfile.objects.create(
            user=self.user,
            position='Терапевт',
            qualification_category='Первая',
            academic_degree='К.м.н.',
            education=[
                {'institution': 'КГМА', 'degree': 'Лечебное дело', 'year': 2012},
                {'institution': 'Старый курс', 'degree': '', 'year': 2020},
            ],
            additional_education=[{'name': 'Курс УЗИ', 'year': 2024}],
            work_experience=[
                {'clinic': 'ГКБ №1', 'position': 'Терапевт', 'from': 2012, 'to': 2018},
                {'clinic': 'МЦ Ак-Жол', 'position': 'Кардиолог', 'from': 2018, 'to': None},
            ],
        )
        self.client.force_authenticate(user=self.user)

    def test_put_uses_flat_professional_fields_without_truncating_work_history(self):
        original_work_experience = self.profile.work_experience.copy()

        response = self.client.put('/api/doctor/profile/', {
            'first_name': 'Алина',
            'last_name': 'Садыкова',
            'position': 'Заведующая отделением',
            'qualification_category': 'Высшая',
            'academic_degree': 'Д.м.н.',
            'education': [{'institution': 'КГМА', 'degree': 'Лечебное дело', 'year': 2012}],
            'additional_education': [
                {'name': 'Курс УЗИ', 'year': 2024},
                {'name': 'Новая программа', 'year': 2025},
            ],
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.position, 'Заведующая отделением')
        self.assertEqual(self.profile.qualification_category, 'Высшая')
        self.assertEqual(self.profile.academic_degree, 'Д.м.н.')
        self.assertEqual(self.profile.work_experience, original_work_experience)
        self.assertEqual(self.profile.additional_education[0]['year'], 2024)
        self.assertEqual(self.profile.additional_education[1]['year'], 2025)

        self.assertEqual(response.data['position'], 'Заведующая отделением')
        self.assertEqual(response.data['additional_education'][1]['name'], 'Новая программа')
