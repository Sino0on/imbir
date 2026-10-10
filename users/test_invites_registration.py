import datetime
import json

from django.utils import timezone
from rest_framework.test import APITestCase

from users.models import (
    ClinicBranch, ClinicInvite, ClinicProfile, DoctorClinicLink, DoctorProfile,
    PhoneVerificationCode, User,
)


class InviteBase(APITestCase):
    def setUp(self):
        self.clinic_user = User.objects.create_user(
            email='inv-clinic@example.com', password='password123', first_name='Clinic', role=User.Role.CLINIC,
        )
        self.clinic = ClinicProfile.objects.create(
            user=self.clinic_user, name='Клиника', city='Бишкек', country='Кыргызстан',
        )
        self.branch = ClinicBranch.objects.create(clinic=self.clinic, name='Восток', address='ул. Токтогула 1')

    def make_invite(self, branch=None, expires_in=None, created_ago=None, **kwargs):
        invite = ClinicInvite.objects.create(
            clinic=self.clinic, branch=branch,
            expires_at=timezone.now() + expires_in if expires_in is not None else None,
            **kwargs,
        )
        if created_ago is not None:
            ClinicInvite.objects.filter(pk=invite.pk).update(created_at=timezone.now() - created_ago)
            invite.refresh_from_db()
        return invite

    def doctor_payload(self, email='inv-doctor@example.com', phone='+996700100200', full_name='Садыкова Алина Тимуровна',
                       **extra):
        PhoneVerificationCode.objects.create(phone=phone, code='1234', is_used=True)
        payload = {
            'password': 'DoctorTest123!',
            'step1': json.dumps({'full_name': full_name, 'email': email, 'phone': phone}),
            'step2': '{}', 'step3': '{}', 'step4': '{}', 'step5': '{}', 'step6': '{}',
            'step7': json.dumps({
                'agree_terms': True, 'agree_privacy': True,
                'agree_data_processing': True, 'agree_publishing': True,
            }),
        }
        payload.update(extra)
        return payload


class InviteValidateByIdTests(InviteBase):
    """K27: ссылка несёт id конкретного инвайта — проверяется ровно он."""

    def validate(self, **params):
        return self.client.get('/api/auth/invite/validate/', params)

    def test_valid_invite_by_id_returns_its_branch(self):
        invite = self.make_invite(branch=self.branch)
        # Более свежий инвайт главного офиса не должен подменять филиал ссылки.
        self.make_invite()
        response = self.validate(invite=str(invite.pk))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['data']['valid'])
        self.assertEqual(response.data['data']['invite_id'], str(invite.pk))
        self.assertEqual(response.data['data']['branch']['id'], self.branch.id)

    def test_deleted_invite_link_stops_working(self):
        invite = self.make_invite()
        invite_id = str(invite.pk)
        self.make_invite()  # другая действующая ссылка клиники
        invite.delete()
        response = self.validate(invite=invite_id)
        self.assertFalse(response.data['data']['valid'])

    def test_deactivated_and_expired_invites_are_invalid(self):
        inactive = self.make_invite(is_active=False)
        expired = self.make_invite(expires_in=-datetime.timedelta(hours=1))
        self.assertFalse(self.validate(invite=str(inactive.pk)).data['data']['valid'])
        self.assertFalse(self.validate(invite=str(expired.pk)).data['data']['valid'])

    def test_garbage_invite_id_is_invalid_not_500(self):
        response = self.validate(invite='not-a-uuid')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['data']['valid'])

    def test_legacy_link_is_not_shadowed_by_fresh_expired_invite(self):
        """N44/K27: свежая просроченная ссылка больше не перекрывает старую действующую."""
        self.make_invite(created_ago=datetime.timedelta(days=2))
        self.make_invite(expires_in=-datetime.timedelta(minutes=1))
        response = self.validate(invite_clinic_id=self.clinic_user.id)
        self.assertTrue(response.data['data']['valid'])

    def test_legacy_link_without_branch_means_main_office(self):
        self.make_invite(branch=self.branch)
        response = self.validate(invite_clinic_id=self.clinic_user.id)
        self.assertFalse(response.data['data']['valid'])

    def test_missing_params_is_400(self):
        self.assertEqual(self.validate().status_code, 400)


class DoctorRegisterWithInviteTests(InviteBase):
    def test_registration_links_doctor_to_invite_branch(self):
        invite = self.make_invite(branch=self.branch)
        self.make_invite()  # более свежая ссылка главного офиса
        response = self.client.post(
            '/api/auth/register/doctor/', self.doctor_payload(invite=str(invite.pk)), format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        link = DoctorClinicLink.objects.get(doctor__user__email='inv-doctor@example.com')
        self.assertEqual(link.clinic, self.clinic)
        self.assertEqual(link.branch, self.branch)

    def test_registration_with_deleted_invite_fails(self):
        invite = self.make_invite()
        invite_id = str(invite.pk)
        self.make_invite()
        invite.delete()
        response = self.client.post(
            '/api/auth/register/doctor/',
            # Новый фронт шлёт и id инвайта, и старые параметры — решает id.
            self.doctor_payload(invite=invite_id, invite_clinic_id=self.clinic_user.id),
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('invite', response.data)
        self.assertFalse(User.objects.filter(email='inv-doctor@example.com').exists())

    def test_legacy_registration_still_works(self):
        self.make_invite()
        response = self.client.post(
            '/api/auth/register/doctor/', self.doctor_payload(invite_clinic_id=self.clinic_user.id), format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(DoctorClinicLink.objects.filter(clinic=self.clinic, branch__isnull=True).exists())


class DoctorRegisterNameTests(InviteBase):
    """K29: ФИО — «Фамилия Имя Отчество»; должность и категория — в свои поля."""

    def test_full_name_split_with_patronymic(self):
        payload = self.doctor_payload(full_name='Садыкова Алина Тимур кызы')
        response = self.client.post('/api/auth/register/doctor/', payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(email='inv-doctor@example.com')
        self.assertEqual(user.last_name, 'Садыкова')
        self.assertEqual(user.first_name, 'Алина')
        self.assertEqual(user.patronymic, 'Тимур кызы')

    def test_position_and_qualification_saved_to_profile_fields(self):
        payload = self.doctor_payload(
            step5=json.dumps({'position': 'Главный врач', 'qualification_category': 'Высшая'}),
        )
        response = self.client.post('/api/auth/register/doctor/', payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        profile = DoctorProfile.objects.get(user__email='inv-doctor@example.com')
        self.assertEqual(profile.position, 'Главный врач')
        self.assertEqual(profile.qualification_category, 'Высшая')
        self.assertEqual(profile.additional_services, '')


class InviteAcceptTests(InviteBase):
    """K28: уже зарегистрированный врач принимает ссылку-приглашение."""

    def setUp(self):
        super().setUp()
        self.doc_user = User.objects.create_user(
            email='inv-existing@example.com', password='password123', first_name='Doc', role=User.Role.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(user=self.doc_user)

    def accept(self, **body):
        return self.client.post('/api/auth/invite/accept/', body, format='json')

    def test_existing_doctor_accepts_invite(self):
        invite = self.make_invite(branch=self.branch)
        self.client.force_authenticate(self.doc_user)
        response = self.accept(invite=str(invite.pk))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data['data']['already_linked'])
        link = DoctorClinicLink.objects.get(doctor=self.doctor, clinic=self.clinic)
        self.assertTrue(link.is_active)
        self.assertEqual(link.branch, self.branch)

    def test_accept_reactivates_detached_link(self):
        DoctorClinicLink.objects.create(doctor=self.doctor, clinic=self.clinic, is_active=False)
        invite = self.make_invite(branch=self.branch)
        self.client.force_authenticate(self.doc_user)
        response = self.accept(invite=str(invite.pk))
        self.assertEqual(response.status_code, 200, response.data)
        link = DoctorClinicLink.objects.get(doctor=self.doctor, clinic=self.clinic)
        self.assertTrue(link.is_active)
        self.assertEqual(link.branch, self.branch)

    def test_already_linked_doctor_keeps_link(self):
        DoctorClinicLink.objects.create(doctor=self.doctor, clinic=self.clinic)
        invite = self.make_invite(branch=self.branch)
        self.client.force_authenticate(self.doc_user)
        response = self.accept(invite=str(invite.pk))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['data']['already_linked'])
        self.assertIsNone(DoctorClinicLink.objects.get(doctor=self.doctor, clinic=self.clinic).branch)

    def test_expired_invite_is_rejected(self):
        invite = self.make_invite(expires_in=-datetime.timedelta(minutes=1))
        self.client.force_authenticate(self.doc_user)
        response = self.accept(invite=str(invite.pk))
        self.assertEqual(response.status_code, 400)
        self.assertFalse(DoctorClinicLink.objects.filter(doctor=self.doctor).exists())

    def test_non_doctor_and_anonymous_cannot_accept(self):
        invite = self.make_invite()
        self.assertEqual(self.accept(invite=str(invite.pk)).status_code, 401)
        patient = User.objects.create_user(email='inv-patient@example.com', password='password123')
        self.client.force_authenticate(patient)
        self.assertEqual(self.accept(invite=str(invite.pk)).status_code, 403)


class PhoneAvailabilityTests(APITestCase):
    """N5: занятость телефона проверяется до последнего шага анкеты."""

    def setUp(self):
        User.objects.create_user(email='inv-taken@example.com', password='password123', phone='+996700999888')

    def test_taken_and_free_phone(self):
        taken = self.client.get('/api/auth/phone/check/', {'phone': '+996700999888'})
        self.assertEqual(taken.status_code, 200)
        self.assertFalse(taken.data['data']['available'])
        free = self.client.post('/api/auth/phone/check/', {'phone': '+996700000111'}, format='json')
        self.assertTrue(free.data['data']['available'])

    def test_empty_phone_is_400(self):
        self.assertEqual(self.client.get('/api/auth/phone/check/').status_code, 400)
