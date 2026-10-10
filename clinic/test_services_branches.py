import datetime

from rest_framework import status
from rest_framework.test import APITestCase

from appointments.models import Appointment
from services.models import Service
from users.models import (
    ClinicBranch, ClinicInvite, ClinicProfile, DoctorClinicLink, DoctorInvitation, DoctorProfile, User,
)


class ClinicServicesBranchesBase(APITestCase):
    def setUp(self):
        self.clinic_user = User.objects.create_user(
            email='sb-clinic@example.com', password='password123', first_name='Clinic', role=User.Role.CLINIC,
        )
        self.clinic = ClinicProfile.objects.create(
            user=self.clinic_user, name='Clinic', city='Бишкек', country='Кыргызстан',
        )
        self.doc_user = User.objects.create_user(
            email='sb-doctor@example.com', password='password123', first_name='Doc', last_name='One',
            role=User.Role.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(user=self.doc_user, city='Бишкек', is_published=True)
        DoctorClinicLink.objects.create(doctor=self.doctor, clinic=self.clinic)

        self.other_doc_user = User.objects.create_user(
            email='sb-doctor2@example.com', password='password123', first_name='Doc', last_name='Two',
            role=User.Role.DOCTOR,
        )
        self.other_doctor = DoctorProfile.objects.create(user=self.other_doc_user, city='Бишкек', is_published=True)
        self.client.force_authenticate(user=self.clinic_user)


class ClinicDoctorDetachServicesTests(ClinicServicesBranchesBase):
    """K18: открепление врача снимает его с процедур клиники, а устаревший id
    в doctor_ids больше не валит сохранение процедуры."""

    def test_detach_removes_doctor_from_clinic_services_only(self):
        service = Service.objects.create(name='УЗИ', category='diagnostics', clinic=self.clinic)
        foreign_clinic_user = User.objects.create_user(
            email='sb-foreign@example.com', password='password123', first_name='F', role=User.Role.CLINIC,
        )
        foreign_clinic = ClinicProfile.objects.create(user=foreign_clinic_user, name='Foreign')
        foreign_service = Service.objects.create(name='ЭКГ', category='diagnostics', clinic=foreign_clinic)
        own_service = Service.objects.create(name='Консультация', category='consult')
        self.doctor.services.add(service, foreign_service, own_service)

        response = self.client.delete(f'/api/clinic/doctors/{self.doc_user.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        self.assertFalse(DoctorClinicLink.objects.filter(doctor=self.doctor, clinic=self.clinic).exists())
        self.assertEqual(
            set(self.doctor.services.values_list('id', flat=True)),
            {foreign_service.id, own_service.id},
        )
        response = self.client.get(f'/api/clinic/services/{service.id}/')
        self.assertEqual(response.data['doctors'], [])

    def test_stale_doctor_id_of_unlinked_doctor_is_ignored_on_update(self):
        service = Service.objects.create(name='УЗИ', category='diagnostics', clinic=self.clinic)
        self.doctor.services.add(service)
        # Связь пропала в обход ручки открепления (например, через админку),
        # а врач остался в doctors процедуры.
        DoctorClinicLink.objects.filter(doctor=self.doctor, clinic=self.clinic).delete()

        response = self.client.put(f'/api/clinic/services/{service.id}/', {
            'name': 'УЗИ сердца',
            'doctor_ids': [self.doc_user.id],
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['name'], 'УЗИ сердца')
        self.assertEqual(response.data['doctors'], [])

    def test_new_unlinked_doctor_still_rejected_on_update(self):
        service = Service.objects.create(name='УЗИ', category='diagnostics', clinic=self.clinic)
        response = self.client.put(f'/api/clinic/services/{service.id}/', {
            'doctor_ids': [self.other_doc_user.id],
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Некоторые врачи не принадлежат этой клинике', str(response.data))

    def test_inactive_link_doctor_cannot_be_assigned(self):
        DoctorClinicLink.objects.filter(doctor=self.doctor, clinic=self.clinic).update(is_active=False)
        response = self.client.post('/api/clinic/services/', {
            'name': 'УЗИ', 'category': 'diagnostics', 'doctor_ids': [self.doc_user.id],
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ClinicServiceDeleteAndPriceTests(ClinicServicesBranchesBase):
    """K19: услугу с записями не удаляют (иначе записи теряют её), K21: цена."""

    def test_service_with_appointments_cannot_be_deleted_but_can_be_deactivated(self):
        service = Service.objects.create(name='УЗИ', category='diagnostics', price=1500, clinic=self.clinic)
        appointment = Appointment.objects.create(
            clinic=self.clinic, service=service, date=datetime.date(2026, 1, 10), time=datetime.time(10, 0),
            status=Appointment.Status.COMPLETED,
        )

        response = self.client.delete(f'/api/clinic/services/{service.id}/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('деактивируйте', response.data['detail'])
        appointment.refresh_from_db()
        self.assertEqual(appointment.service_id, service.id)

        response = self.client.put(f'/api/clinic/services/{service.id}/', {'is_active': False}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['is_active'])

    def test_service_without_appointments_is_deleted(self):
        service = Service.objects.create(name='УЗИ', category='diagnostics', clinic=self.clinic)
        response = self.client.delete(f'/api/clinic/services/{service.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Service.objects.filter(pk=service.id).exists())

    def test_negative_price_rejected_and_price_can_be_cleared(self):
        response = self.client.post('/api/clinic/services/', {
            'name': 'УЗИ', 'category': 'diagnostics', 'price': '-500',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('price', response.data)

        response = self.client.post('/api/clinic/services/', {
            'name': 'УЗИ', 'category': 'diagnostics', 'price': '1500',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        detail_url = f"/api/clinic/services/{response.data['id']}/"

        response = self.client.put(detail_url, {'price': None}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['price'])

        # multipart (вместе с фото): пустая строка тоже очищает цену.
        self.client.put(detail_url, {'price': '900'}, format='json')
        response = self.client.put(detail_url, {'price': ''}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['price'])


class ClinicBranchCrudTests(ClinicServicesBranchesBase):
    """N15: филиал можно завести, править целиком и удалить."""

    def test_create_update_all_fields_and_delete_branch(self):
        response = self.client.post('/api/clinic/branches/', {
            'name': 'На Чуй', 'address': 'пр. Чуй, 100', 'phone': '+996555000111',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        branch_id = response.data['id']
        url = f'/api/clinic/branches/{branch_id}/'

        # PUT только с адресом (как шлёт текущий фронт) не стирает остальное.
        response = self.client.put(url, {'address': 'пр. Чуй, 101'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'На Чуй')
        self.assertEqual(response.data['address'], 'пр. Чуй, 101')

        schedule = {'monday': {'enabled': True, 'from': '09:00', 'to': '18:00'}}
        response = self.client.patch(url, {
            'name': 'Центр', 'phone': '+996555000222', 'schedule': schedule,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Центр')
        self.assertEqual(response.data['phone'], '+996555000222')
        self.assertEqual(response.data['schedule'], schedule)

        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ClinicBranch.objects.filter(pk=branch_id).exists())

    def test_delete_branch_keeps_doctor_links_services_and_invites(self):
        branch = ClinicBranch.objects.create(clinic=self.clinic, name='Филиал', address='ул. Токтогула, 1')
        DoctorClinicLink.objects.filter(doctor=self.doctor, clinic=self.clinic).update(branch=branch)
        service = Service.objects.create(name='УЗИ', category='diagnostics', clinic=self.clinic, branch=branch)
        invite = ClinicInvite.objects.create(clinic=self.clinic, branch=branch)
        invitation = DoctorInvitation.objects.create(clinic=self.clinic, doctor=self.other_doctor, branch=branch)

        response = self.client.delete(f'/api/clinic/branches/{branch.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        link = DoctorClinicLink.objects.get(doctor=self.doctor, clinic=self.clinic)
        self.assertIsNone(link.branch_id)
        service.refresh_from_db()
        self.assertIsNone(service.branch_id)
        invite.refresh_from_db()
        self.assertIsNone(invite.branch_id)
        invitation.refresh_from_db()
        self.assertIsNone(invitation.branch_id)

    def test_other_clinic_cannot_touch_branch(self):
        branch = ClinicBranch.objects.create(clinic=self.clinic, address='ул. Токтогула, 1')
        other_user = User.objects.create_user(
            email='sb-other-clinic@example.com', password='password123', first_name='O', role=User.Role.CLINIC,
        )
        ClinicProfile.objects.create(user=other_user, name='Other')
        self.client.force_authenticate(user=other_user)
        self.assertEqual(
            self.client.delete(f'/api/clinic/branches/{branch.id}/').status_code, status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.patch(f'/api/clinic/branches/{branch.id}/', {'name': 'X'}, format='json').status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertTrue(ClinicBranch.objects.filter(pk=branch.id).exists())
