from rest_framework.test import APITestCase
import json

from rest_framework import status
from django.core.files.uploadedfile import SimpleUploadedFile
from references.models import Specialization
from users.models import ClinicBranch, User, ClinicProfile, DoctorProfile, DoctorClinicLink


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


class ClinicDoctorProfileApiTests(APITestCase):
    """Полный сценарий: клиника создаёт, читает и редактирует карточку врача."""

    def setUp(self):
        self.clinic_user = User.objects.create_user(
            email='clinic-profile@example.com', password='password123',
            first_name='Clinic', role=User.Role.CLINIC,
        )
        self.clinic = ClinicProfile.objects.create(
            user=self.clinic_user, name='Clinic', city='Бишкек', country='Кыргызстан',
        )
        self.other_clinic_user = User.objects.create_user(
            email='other-clinic@example.com', password='password123',
            first_name='Other clinic', role=User.Role.CLINIC,
        )
        ClinicProfile.objects.create(
            user=self.other_clinic_user, name='Other clinic', city='Ош', country='Кыргызстан',
        )
        self.primary_specialization = Specialization.objects.create(name='Терапия')
        self.narrow_specialization = Specialization.objects.create(name='Кардиология')

    def create_doctor(self):
        self.client.force_authenticate(user=self.clinic_user)
        response = self.client.post('/api/clinic/doctors/', {
            'first_name': 'Алина',
            'last_name': 'Садыкова',
            'email': 'alina@example.com',
            'phone': '+996777000222',
            'gender': 'female',
            'birth_date': '1990-02-03',
            'city': 'Бишкек',
            'languages': ['Русский', 'Кыргызский'],
            'primary_specialization_ids': [self.primary_specialization.id],
            'narrow_specialization_ids': [self.narrow_specialization.id],
            'experience_years': 12,
            'position': 'Врач-терапевт',
            'qualification_category': 'Высшая',
            'academic_degree': 'К.м.н.',
            'education': [{
                'institution': 'КГМА', 'year': 2012, 'internship': 'Терапия',
                'residency': 'Кардиология', 'diploma_specialization': 'Лечебное дело',
            }],
            'additional_education': [{'name': 'Кардиология', 'year': 2024}],
            'license_number': 'ЛИЦ-12345',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        return User.objects.get(email='alina@example.com')

    def test_clinic_can_create_read_and_patch_its_doctor_profile(self):
        doctor_user = self.create_doctor()
        detail_url = f'/api/clinic/doctors/{doctor_user.id}/'

        profile = DoctorProfile.objects.get(user=doctor_user)
        self.assertEqual(profile.gender, 'female')
        self.assertEqual(profile.languages, ['Русский', 'Кыргызский'])
        self.assertEqual(profile.position, 'Врач-терапевт')
        self.assertEqual(profile.education[0]['institution'], 'КГМА')
        self.assertTrue(profile.primary_specializations.filter(pk=self.primary_specialization.pk).exists())

        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['birth_date'], '1990-02-03')
        self.assertEqual(response.data['license_number'], 'ЛИЦ-12345')
        self.assertEqual(response.data['primary_specializations'][0]['id'], self.primary_specialization.id)

        response = self.client.patch(detail_url, {
            'experience_years': 13,
            'position': 'Заведующая отделением',
            'languages': ['Русский', 'Английский'],
            'narrow_specialization_ids': [],
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        profile.refresh_from_db()
        self.assertEqual(profile.experience_years, 13)
        self.assertEqual(profile.position, 'Заведующая отделением')
        self.assertEqual(profile.languages, ['Русский', 'Английский'])
        self.assertFalse(profile.narrow_specializations.exists())

    def test_other_clinic_cannot_read_or_update_doctor(self):
        doctor_user = self.create_doctor()
        detail_url = f'/api/clinic/doctors/{doctor_user.id}/'
        self.client.force_authenticate(user=self.other_clinic_user)

        self.assertEqual(self.client.get(detail_url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            self.client.patch(detail_url, {'position': 'Не должен измениться'}, format='json').status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_clinic_can_manage_doctor_documents_after_creation(self):
        doctor_user = self.create_doctor()
        documents_url = f'/api/clinic/doctors/{doctor_user.id}/documents/'
        certificate = SimpleUploadedFile('certificate.pdf', b'certificate', content_type='application/pdf')

        response = self.client.post(documents_url, {'file': certificate}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        document_id = response.data['id']
        self.assertEqual(self.client.get(documents_url).status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.client.delete(f'{documents_url}{document_id}/').status_code,
            status.HTTP_204_NO_CONTENT,
        )


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


class ClinicServiceProfileApiTests(APITestCase):
    """Карточка процедуры: фото, филиал, собственный график и изоляция клиник."""

    def setUp(self):
        self.clinic_user = User.objects.create_user(
            email='procedures-clinic@example.com', password='password123',
            first_name='Clinic', role=User.Role.CLINIC,
        )
        self.clinic = ClinicProfile.objects.create(
            user=self.clinic_user, name='Clinic', city='Бишкек', country='Кыргызстан',
        )
        self.branch = ClinicBranch.objects.create(
            clinic=self.clinic, name='На Чуй', address='пр. Чуй, 100',
        )
        self.other_clinic_user = User.objects.create_user(
            email='other-procedures-clinic@example.com', password='password123',
            first_name='Other clinic', role=User.Role.CLINIC,
        )
        self.other_clinic = ClinicProfile.objects.create(
            user=self.other_clinic_user, name='Other clinic', city='Ош', country='Кыргызстан',
        )
        self.other_branch = ClinicBranch.objects.create(
            clinic=self.other_clinic, name='Чужой филиал', address='ул. Ленина, 1',
        )

    def test_clinic_can_create_read_and_update_full_service_card(self):
        self.client.force_authenticate(user=self.clinic_user)
        photo = SimpleUploadedFile(
            'procedure.gif',
            b'GIF87a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02L\x01\x00;',
            content_type='image/gif',
        )
        response = self.client.post('/api/clinic/services/', {
            'name': 'УЗИ сердца',
            'category': 'diagnostics',
            'description': 'Исследование сердца',
            'price': '1500.00',
            'duration': 30,
            'branch_id': self.branch.id,
            'schedule': json.dumps({'monday': {'enabled': True, 'from': '09:00', 'to': '17:00'}}),
            'lunch_break': json.dumps({'from': '13:00', 'to': '14:00'}),
            'photo': photo,
        }, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['description'], 'Исследование сердца')
        self.assertEqual(response.data['branch']['id'], self.branch.id)
        self.assertEqual(response.data['schedule']['monday']['from'], '09:00')
        self.assertIsNotNone(response.data['photo'])

        service_id = response.data['id']
        detail_url = f'/api/clinic/services/{service_id}/'
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['branch']['address'], 'пр. Чуй, 100')

        response = self.client.put(detail_url, {
            'description': 'Обновлённое исследование сердца',
            'schedule': {'tuesday': {'enabled': True, 'from': '10:00', 'to': '16:00'}},
            'lunch_break': {'from': '12:30', 'to': '13:00'},
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['description'], 'Обновлённое исследование сердца')
        self.assertEqual(response.data['schedule']['tuesday']['to'], '16:00')
        self.assertEqual(response.data['lunch_break']['from'], '12:30')

    def test_service_rejects_foreign_branch_and_is_hidden_from_other_clinic(self):
        self.client.force_authenticate(user=self.clinic_user)
        response = self.client.post('/api/clinic/services/', {
            'name': 'Массаж', 'category': 'massage', 'branch_id': self.other_branch.id,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('не принадлежит вашей клинике', str(response.data))

        from services.models import Service
        service = Service.objects.create(name='Массаж', category='massage', clinic=self.clinic)
        self.client.force_authenticate(user=self.other_clinic_user)
        self.assertEqual(
            self.client.get(f'/api/clinic/services/{service.id}/').status_code,
            status.HTTP_404_NOT_FOUND,
        )

