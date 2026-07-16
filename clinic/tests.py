from rest_framework.test import APITestCase
from rest_framework import status
from users.models import User, ClinicProfile, DoctorProfile, DoctorClinicLink


class ClinicCreateDoctorTests(APITestCase):
    def setUp(self):
        # Create a clinic user and profile
        self.clinic_user = User.objects.create_user(
            email='clinic@example.com', password='password123', first_name='Clinic Name', role=User.Role.CLINIC
        )
        self.clinic = ClinicProfile.objects.create(
            user=self.clinic_user, name='Clinic Name', city='Бишкек', country='Кыргызстан', is_published=True
        )

        self.patient = User.objects.create_user(
            email='patient@example.com', password='password123', first_name='Ivan', role=User.Role.PATIENT
        )

        self.create_doctor_url = '/api/clinic/doctors/'

    def test_create_doctor_unauthorized(self):
        response = self.client.post(self.create_doctor_url, {
            'first_name': 'Асан',
            'last_name': 'Усенов',
            'email': 'doctor_asan@example.com'
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_doctor_forbidden_role(self):
        self.client.force_authenticate(user=self.patient)
        response = self.client.post(self.create_doctor_url, {
            'first_name': 'Асан',
            'last_name': 'Усенов',
            'email': 'doctor_asan@example.com'
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_doctor_success_with_default_password(self):
        self.client.force_authenticate(user=self.clinic_user)
        response = self.client.post(self.create_doctor_url, {
            'first_name': 'Асан',
            'last_name': 'Усенов',
            'email': 'doctor_asan@example.com',
            'phone': '+996777000111'
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Assert User creation
        new_user = User.objects.get(email='doctor_asan@example.com')
        self.assertEqual(new_user.role, User.Role.DOCTOR)
        self.assertEqual(new_user.first_name, 'Асан')
        self.assertEqual(new_user.last_name, 'Усенов')
        self.assertEqual(new_user.phone, '+996777000111')
        
        # Verify default password works
        self.assertTrue(new_user.check_password('Doctor123!'))

        # Assert DoctorProfile creation and inherited location
        profile = DoctorProfile.objects.get(user=new_user)
        self.assertEqual(profile.city, 'Бишкек')
        self.assertEqual(profile.country, 'Кыргызстан')
        self.assertTrue(profile.is_published)

        # Assert DoctorClinicLink creation
        self.assertTrue(DoctorClinicLink.objects.filter(doctor=profile, clinic=self.clinic).exists())

        # Assert response details
        self.assertEqual(response.data['full_name'], 'Асан Усенов')

    def test_create_doctor_success_with_custom_password(self):
        self.client.force_authenticate(user=self.clinic_user)
        response = self.client.post(self.create_doctor_url, {
            'first_name': 'Марат',
            'last_name': 'Садыков',
            'email': 'doctor_marat@example.com',
            'password': 'CustomPassword123!'
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        new_user = User.objects.get(email='doctor_marat@example.com')
        self.assertTrue(new_user.check_password('CustomPassword123!'))

    def test_create_doctor_duplicate_email(self):
        self.client.force_authenticate(user=self.clinic_user)
        # Attempt with existing email (patient)
        response = self.client.post(self.create_doctor_url, {
            'first_name': 'Асан',
            'last_name': 'Усенов',
            'email': 'patient@example.com'
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Пользователь с такой почтой уже существует.', str(response.data))


class ClinicServiceDoctorAssignmentTests(APITestCase):
    def setUp(self):
        # Clinic
        self.clinic_user = User.objects.create_user(
            email='clinic@example.com', password='password123', first_name='Clinic Name', role=User.Role.CLINIC
        )
        self.clinic = ClinicProfile.objects.create(
            user=self.clinic_user, name='Clinic Name', city='Бишкек', country='Кыргызстан', is_published=True
        )

        # Linked doctor
        self.doc_user = User.objects.create_user(
            email='doctor@example.com', password='password123', first_name='Doc', last_name='One', role=User.Role.DOCTOR
        )
        self.doctor = DoctorProfile.objects.create(
            user=self.doc_user, city='Бишкек', is_published=True
        )
        DoctorClinicLink.objects.create(doctor=self.doctor, clinic=self.clinic)

        # Non-linked doctor
        self.other_doc_user = User.objects.create_user(
            email='other_doctor@example.com', password='password123', first_name='Doc', last_name='Two', role=User.Role.DOCTOR
        )
        self.other_doctor = DoctorProfile.objects.create(
            user=self.other_doc_user, city='Бишкек', is_published=True
        )

        self.services_url = '/api/clinic/services/'

    def test_create_service_with_doctors(self):
        self.client.force_authenticate(user=self.clinic_user)
        response = self.client.post(self.services_url, {
            'name': 'УЗИ сердца',
            'category': 'diagnostics',
            'price': '1500.00',
            'doctor_ids': [self.doc_user.id]
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data['doctors']), 1)
        self.assertEqual(response.data['doctors'][0]['id'], self.doc_user.id)

        # Verify database link
        self.doctor.refresh_from_db()
        self.assertEqual(self.doctor.services.count(), 1)

    def test_create_service_with_invalid_doctor(self):
        self.client.force_authenticate(user=self.clinic_user)
        # Attempt to link other_doctor who is not linked to this clinic
        response = self.client.post(self.services_url, {
            'name': 'УЗИ сердца',
            'category': 'diagnostics',
            'price': '1500.00',
            'doctor_ids': [self.other_doc_user.id]
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Некоторые врачи не принадлежат этой клинике', str(response.data))

    def test_update_service_doctors(self):
        # Create service first
        from services.models import Service
        service = Service.objects.create(name='Original Service', category='diagnostics', price=1000, clinic=self.clinic)
        self.doctor.services.add(service)

        self.client.force_authenticate(user=self.clinic_user)
        detail_url = f'/api/clinic/services/{service.pk}/'

        # Update and clear doctor_ids
        response = self.client.put(detail_url, {
            'name': 'Updated Service',
            'category': 'diagnostics',
            'price': '1200.00',
            'doctor_ids': []
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['doctors']), 0)
        self.doctor.refresh_from_db()
        self.assertEqual(self.doctor.services.count(), 0)

