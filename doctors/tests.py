from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from users.models import DoctorProfile
from doctors.models import Interview

User = get_user_model()

class DoctorAvailableSlotsTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='doctor@example.com',
            password='password123',
            first_name='Doctor',
            last_name='Who',
            role=User.Role.DOCTOR
        )
        self.doctor_profile = DoctorProfile.objects.create(
            user=self.user,
            is_published=True,
            schedule={
                "friday": {"to": "17:00", "from": "09:00", "enabled": True},
                "monday": {"to": "18:00", "from": "09:00", "enabled": True},
                "sunday": {"to": None, "from": None, "enabled": False},
                "tuesday": {"to": "18:00", "from": "09:00", "enabled": True},
                "saturday": {"to": None, "from": None, "enabled": False},
                "thursday": {"to": "18:00", "from": "09:00", "enabled": True},
                "wednesday": {"to": "16:00", "from": "10:00", "enabled": True}
            },
            lunch_break={"from": "13:00", "to": "14:00"}
        )
        self.url = f'/api/doctors/{self.user.id}/available-slots/'

    def test_available_slots_monday_success(self):
        # 2026-07-06 is Monday, working 09:00 to 18:00
        response = self.client.get(self.url, {'date': '2026-07-06'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['date'], '2026-07-06')
        
        slots = response.data['slots']
        self.assertEqual(len(slots), 18)
        
        self.assertEqual(slots[0]['time'], '09:00')
        self.assertEqual(slots[-1]['time'], '17:30')
        
        # Check lunch break slots (13:00 - 14:00 should not be available)
        lunch_slots = [s for s in slots if s['time'] in ['13:00', '13:30']]
        for s in lunch_slots:
            self.assertFalse(s['available'])

    def test_available_slots_sunday_disabled(self):
        # 2026-07-05 is Sunday
        response = self.client.get(self.url, {'date': '2026-07-05'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['slots']), 0)


class DoctorInterviewsAPITests(APITestCase):
    def setUp(self):
        # Create a doctor user and profile
        self.doctor_user = User.objects.create_user(
            email='doctor@example.com',
            password='password123',
            first_name='Doctor',
            last_name='Who',
            role=User.Role.DOCTOR
        )
        self.doctor_profile = DoctorProfile.objects.create(
            user=self.doctor_user,
            is_published=True
        )

        # Create a patient user
        self.patient_user = User.objects.create_user(
            email='patient@example.com',
            password='password123',
            first_name='John',
            last_name='Doe',
            role=User.Role.PATIENT
        )

        # URLs
        self.list_create_url = '/api/doctor/interviews/'
        self.public_detail_url = f'/api/doctors/{self.doctor_user.id}/'

    def test_interviews_access_permissions(self):
        # Try to list without login
        response = self.client.get(self.list_create_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        # Try to list as patient
        self.client.force_authenticate(user=self.patient_user)
        response = self.client.get(self.list_create_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_doctor_interview_crud_lifecycle(self):
        self.client.force_authenticate(user=self.doctor_user)

        # 1. List (initially empty)
        response = self.client.get(self.list_create_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']), 0)

        # 2. Create
        data = {
            'title': 'Интервью о здоровье',
            'video_url': 'https://youtube.com/watch?v=12345',
            'priority': 2
        }
        response = self.client.post(self.list_create_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], 'Интервью о здоровье')
        self.assertEqual(response.data['video_url'], 'https://youtube.com/watch?v=12345')
        self.assertEqual(response.data['priority'], 2)
        interview_id = response.data['id']

        # Verify in DB
        self.assertTrue(Interview.objects.filter(id=interview_id, doctor=self.doctor_profile).exists())

        # 3. Retrieve & Update
        detail_url = f'{self.list_create_url}{interview_id}/'
        update_data = {
            'title': 'Обновленное интервью',
            'video_url': 'https://youtube.com/watch?v=updated',
            'priority': 3
        }
        response = self.client.put(detail_url, update_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Обновленное интервью')
        self.assertEqual(response.data['priority'], 3)

        # 4. List now has 1 item
        response = self.client.get(self.list_create_url)
        self.assertEqual(len(response.data['data']), 1)

        # 5. Delete
        response = self.client.delete(detail_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Interview.objects.filter(id=interview_id).exists())

    def test_interviews_ordering_and_public_api(self):
        # Create a few interviews
        Interview.objects.create(doctor=self.doctor_profile, title='Low', video_url='http://yt/low', priority=0)
        Interview.objects.create(doctor=self.doctor_profile, title='High', video_url='http://yt/high', priority=3)
        Interview.objects.create(doctor=self.doctor_profile, title='Medium', video_url='http://yt/med', priority=1)

        # Retrieve public detail
        response = self.client.get(self.public_detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        interviews = response.data['interviews']
        self.assertEqual(len(interviews), 3)
        # Verify ordering: priority 3 -> 1 -> 0
        self.assertEqual(interviews[0]['title'], 'High')
        self.assertEqual(interviews[1]['title'], 'Medium')
        self.assertEqual(interviews[2]['title'], 'Low')


class GlobalSearchTests(APITestCase):
    def setUp(self):
        # Create doctors
        self.doc_user = User.objects.create_user(
            email='doc_search@example.com',
            password='password123',
            first_name='Андрей',
            last_name='Иванов',
            role=User.Role.DOCTOR
        )
        self.doctor = DoctorProfile.objects.create(
            user=self.doc_user,
            is_published=True,
            primary_specializations=["Кардиолог"]
        )

        # Create clinics
        self.clinic_user = User.objects.create_user(
            email='clinic_search@example.com',
            password='password123',
            first_name='Clinic',
            last_name='Search',
            role=User.Role.CLINIC
        )
        from users.models import ClinicProfile
        self.clinic = ClinicProfile.objects.create(
            user=self.clinic_user,
            name='Клиника Кардиологии',
            is_published=True
        )

        # Create services
        from services.models import Service
        self.service = Service.objects.create(
            name='УЗИ сердца (ЭхоКГ)',
            price=2500.00,
            category='diagnostics',
            is_active=True
        )
        self.service.doctors.add(self.doctor)

        self.suggest_url = '/api/search/suggest/'
        self.extended_url = '/api/search/'

    def test_search_suggest_success(self):
        response = self.client.get(self.suggest_url, {'q': 'Кардиоло'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        self.assertIn('doctors', response.data)
        self.assertIn('clinics', response.data)
        self.assertIn('services', response.data)

        # Doctor matched on specialization
        self.assertEqual(len(response.data['doctors']), 1)
        self.assertEqual(response.data['doctors'][0]['full_name'], 'Андрей Иванов')
        self.assertEqual(response.data['doctors'][0]['specialty'], 'Кардиолог')

        # Clinic matched on name
        self.assertEqual(len(response.data['clinics']), 1)
        self.assertEqual(response.data['clinics'][0]['name'], 'Клиника Кардиологии')

    def test_search_extended_success(self):
        response = self.client.get(self.extended_url, {'q': 'сердца'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertIn('doctors', response.data)
        self.assertIn('clinics', response.data)
        self.assertIn('services', response.data)

        # Service matched on name
        self.assertEqual(len(response.data['services']), 1)
        self.assertEqual(response.data['services'][0]['name'], 'УЗИ сердца (ЭхоКГ)')

    def test_empty_query(self):
        response = self.client.get(self.suggest_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['doctors']), 0)


from unittest.mock import patch

class GeolocationMiddlewareTests(APITestCase):
    def setUp(self):
        # Create doctors in different cities
        self.doc_user_1 = User.objects.create_user(
            email='doc_bishkek@example.com',
            password='password123',
            first_name='Асан',
            last_name='Бишкекский',
            role=User.Role.DOCTOR
        )
        self.doc_1 = DoctorProfile.objects.create(
            user=self.doc_user_1,
            is_published=True,
            city='Бишкек'
        )

        self.doc_user_2 = User.objects.create_user(
            email='doc_almaty@example.com',
            password='password123',
            first_name='Алихан',
            last_name='Алматинский',
            role=User.Role.DOCTOR
        )
        self.doc_2 = DoctorProfile.objects.create(
            user=self.doc_user_2,
            is_published=True,
            city='Алматы'
        )

        self.doctors_list_url = '/api/doctors/'

    def test_default_city_filtering_without_params(self):
        # By default, middleware sets city to DEFAULT_CITY ('Бишкек')
        # So calling list view without params should return only doctors from Бишкек
        response = self.client.get(self.doctors_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # StandardPagination wraps data under 'data'
        results = response.data['data']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], self.doc_user_1.id)

    def test_override_city_via_query_param(self):
        # Query specifically for Алматы
        response = self.client.get(self.doctors_list_url, {'city': 'Алматы'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['data']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], self.doc_user_2.id)

    @patch('core.middleware.get_city_from_ip')
    def test_ip_geolocation_filtering(self, mock_get_city):
        # Mock geolocation to return 'Алматы' for a simulated external IP
        mock_get_city.return_value = 'Алматы'
        
        # Simulate request with standard X-Forwarded-For header
        response = self.client.get(self.doctors_list_url, HTTP_X_FORWARDED_FOR='123.45.67.89')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['data']
        self.assertEqual(results[0]['id'], self.doc_user_2.id)


class DoctorAndClinicFilterTests(APITestCase):
    def setUp(self):
        # Create doctors with different experience
        self.doc_user_1 = User.objects.create_user(
            email='doc1@example.com', password='password123', first_name='Doc', last_name='One', role=User.Role.DOCTOR
        )
        self.doc_1 = DoctorProfile.objects.create(
            user=self.doc_user_1, is_published=True, experience_years=3, consultation_price=1000, city='Бишкек'
        )

        self.doc_user_2 = User.objects.create_user(
            email='doc2@example.com', password='password123', first_name='Doc', last_name='Two', role=User.Role.DOCTOR
        )
        self.doc_2 = DoctorProfile.objects.create(
            user=self.doc_user_2, is_published=True, experience_years=10, consultation_price=2000, city='Бишкек'
        )

        # Create clinics with different experience and services
        self.clinic_user_1 = User.objects.create_user(
            email='clinic1@example.com', password='password123', first_name='Clinic', last_name='One', role=User.Role.CLINIC
        )
        from users.models import ClinicProfile
        self.clinic_1 = ClinicProfile.objects.create(
            user=self.clinic_user_1, name='Clinic One', is_published=True, experience_years=2, city='Бишкек'
        )

        self.clinic_user_2 = User.objects.create_user(
            email='clinic2@example.com', password='password123', first_name='Clinic', last_name='Two', role=User.Role.CLINIC
        )
        self.clinic_2 = ClinicProfile.objects.create(
            user=self.clinic_user_2, name='Clinic Two', is_published=True, experience_years=15, city='Бишкек'
        )

        # Add services to clinics
        from services.models import Service
        self.service_1 = Service.objects.create(
            name='Service One', price=500.00, category='diagnostics', is_active=True, clinic=self.clinic_1
        )
        self.service_2 = Service.objects.create(
            name='Service Two', price=1500.00, category='diagnostics', is_active=True, clinic=self.clinic_2
        )

        self.doctors_url = '/api/doctors/'
        self.clinics_url = '/api/clinics/'

    def test_doctor_experience_filters(self):
        # 1. min_experience
        response = self.client.get(self.doctors_url, {'min_experience': 5, 'city': 'Бишкек'})
        self.assertEqual(len(response.data['data']), 1)
        self.assertEqual(response.data['data'][0]['id'], self.doc_user_2.id)

        # 2. max_experience
        response = self.client.get(self.doctors_url, {'max_experience': 5, 'city': 'Бишкек'})
        self.assertEqual(len(response.data['data']), 1)
        self.assertEqual(response.data['data'][0]['id'], self.doc_user_1.id)

    def test_clinic_experience_filters(self):
        # 1. min_experience
        response = self.client.get(self.clinics_url, {'min_experience': 5, 'city': 'Бишкек'})
        self.assertEqual(len(response.data['data']), 1)
        self.assertEqual(response.data['data'][0]['id'], self.clinic_user_2.id)

        # 2. max_experience
        response = self.client.get(self.clinics_url, {'max_experience': 5, 'city': 'Бишкек'})
        self.assertEqual(len(response.data['data']), 1)
        self.assertEqual(response.data['data'][0]['id'], self.clinic_user_1.id)

    def test_clinic_price_range_filters(self):
        # Filter clinics having service price <= 1000
        response = self.client.get(self.clinics_url, {'max_price': 1000, 'city': 'Бишкек'})
        self.assertEqual(len(response.data['data']), 1)
        self.assertEqual(response.data['data'][0]['id'], self.clinic_user_1.id)

        # Filter clinics having service price >= 1000
        response = self.client.get(self.clinics_url, {'min_price': 1000, 'city': 'Бишкек'})
        self.assertEqual(len(response.data['data']), 1)
        self.assertEqual(response.data['data'][0]['id'], self.clinic_user_2.id)




