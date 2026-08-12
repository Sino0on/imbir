import json

from django.core import mail
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from users.models import PasswordResetCode, PhoneVerificationCode, EmailVerificationCode, LoginCode

User = get_user_model()

class PasswordResetTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='oldpassword123',
            first_name='Test',
            last_name='User',
            phone='+996777888999'
        )
        self.request_url = '/api/auth/password-reset/'
        self.verify_url = '/api/auth/password-reset/verify/'
        self.confirm_url = '/api/auth/password-reset/confirm/'

    def test_request_password_reset_existing_user(self):
        response = self.client.post(self.request_url, {'email': 'test@example.com'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['detail'],
            'Если пользователь существует, письмо с кодом подтверждения отправлено.'
        )

        # Check DB record
        self.assertTrue(PasswordResetCode.objects.filter(email='test@example.com').exists())
        reset_code = PasswordResetCode.objects.filter(email='test@example.com').first()
        self.assertEqual(len(reset_code.code), 6)
        self.assertFalse(reset_code.is_used)

        # Check sent email
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(reset_code.code, mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to, ['test@example.com'])

    def test_request_password_reset_nonexistent_user(self):
        response = self.client.post(self.request_url, {'email': 'nonexistent@example.com'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['detail'],
            'Если пользователь существует, письмо с кодом подтверждения отправлено.'
        )

        # No DB code generated
        self.assertFalse(PasswordResetCode.objects.filter(email='nonexistent@example.com').exists())
        # No email sent
        self.assertEqual(len(mail.outbox), 0)

    def test_verify_correct_code(self):
        reset_code = PasswordResetCode.objects.create(email='test@example.com', code='123456')
        
        response = self.client.post(self.verify_url, {
            'email': 'test@example.com',
            'code': '123456'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['detail'], 'Код подтверждён успешно.')

    def test_verify_incorrect_code(self):
        reset_code = PasswordResetCode.objects.create(email='test@example.com', code='123456')
        
        response = self.client.post(self.verify_url, {
            'email': 'test@example.com',
            'code': '654321'
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('code', response.data)

    def test_verify_expired_code(self):
        reset_code = PasswordResetCode.objects.create(email='test@example.com', code='123456')
        # Backdate the code's creation time
        reset_code.created_at = timezone.now() - timezone.timedelta(minutes=16)
        reset_code.save()

        response = self.client.post(self.verify_url, {
            'email': 'test@example.com',
            'code': '123456'
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('code', response.data)
        # Note: Depending on serializer format, this could be code: {non_field_errors} or similar, or directly dict key
        self.assertIn('Срок действия кода истёк', str(response.data))

    def test_confirm_reset_success(self):
        reset_code = PasswordResetCode.objects.create(email='test@example.com', code='123456')

        response = self.client.post(self.confirm_url, {
            'email': 'test@example.com',
            'code': '123456',
            'password': 'newsecretpassword123'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['detail'], 'Пароль успешно сброшен')

        # Check DB update
        reset_code.refresh_from_db()
        self.assertTrue(reset_code.is_used)

        # Check user can login with new password
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('newsecretpassword123'))

    def test_confirm_reset_invalid_password(self):
        reset_code = PasswordResetCode.objects.create(email='test@example.com', code='123456')

        response = self.client.post(self.confirm_url, {
            'email': 'test@example.com',
            'code': '123456',
            'password': 'short'
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)

    def test_request_password_reset_existing_phone(self):
        response = self.client.post(self.request_url, {'phone': '+996777888999'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['detail'],
            'Если пользователь существует, СМС с кодом подтверждения отправлено.'
        )

        self.assertTrue(PasswordResetCode.objects.filter(phone='+996777888999').exists())
        reset_code = PasswordResetCode.objects.filter(phone='+996777888999').first()
        self.assertEqual(len(reset_code.code), 6)

    def test_verify_correct_code_phone(self):
        PasswordResetCode.objects.create(phone='+996777888999', code='111222')
        response = self.client.post(self.verify_url, {
            'phone': '+996777888999',
            'code': '111222'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_confirm_reset_success_phone(self):
        reset_code = PasswordResetCode.objects.create(phone='+996777888999', code='111222')
        response = self.client.post(self.confirm_url, {
            'phone': '+996777888999',
            'code': '111222',
            'password': 'newsecretpassword999'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        reset_code.refresh_from_db()
        self.assertTrue(reset_code.is_used)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('newsecretpassword999'))


class PhoneRegistrationTests(APITestCase):
    def setUp(self):
        self.request_url = '/api/auth/register/phone/request/'
        self.confirm_url = '/api/auth/register/phone/confirm/'
        self.login_url = '/api/auth/login/'

    def test_request_code_success(self):
        response = self.client.post(self.request_url, {'phone': '+996700111222'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['detail'], 'Код подтверждения отправлен на указанный номер телефона.')

        self.assertTrue(PhoneVerificationCode.objects.filter(phone='+996700111222').exists())
        verification = PhoneVerificationCode.objects.filter(phone='+996700111222').first()
        self.assertEqual(len(verification.code), 4)

    def test_request_code_duplicate_phone_fails(self):
        User.objects.create_user(
            email='existing@example.com',
            password='password123',
            first_name='Existing',
            last_name='User',
            phone='+996700111222'
        )

        response = self.client.post(self.request_url, {'phone': '+996700111222'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('phone', response.data)

    def test_confirm_registration_success(self):
        verification = PhoneVerificationCode.objects.create(phone='+996700111222', code='4321')

        response = self.client.post(self.confirm_url, {
            'phone': '+996700111222',
            'code': '4321',
            'password': 'newpassword123',
            'first_name': 'Jan',
            'last_name': 'Kovalski'
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertEqual(response.data['user']['first_name'], 'Jan')
        
        verification.refresh_from_db()
        self.assertTrue(verification.is_used)

        user = User.objects.get(phone='+996700111222')
        self.assertEqual(user.first_name, 'Jan')
        self.assertEqual(user.role, User.Role.PATIENT)
        self.assertEqual(user.email, '996700111222@phone.imbir.kg')

        login_response = self.client.post(self.login_url, {
            'email': '+996700111222',
            'password': 'newpassword123'
        })
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        self.assertIn('access', login_response.data)

        login_response_email = self.client.post(self.login_url, {
            'email': '996700111222@phone.imbir.kg',
            'password': 'newpassword123'
        })
        self.assertEqual(login_response_email.status_code, status.HTTP_200_OK)

    def test_confirm_registration_incorrect_code(self):
        verification = PhoneVerificationCode.objects.create(phone='+996700111222', code='4321')

        response = self.client.post(self.confirm_url, {
            'phone': '+996700111222',
            'code': '0000',
            'password': 'newpassword123',
            'first_name': 'Jan',
            'last_name': 'Kovalski'
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('code', response.data)

    def test_confirm_registration_expired_code(self):
        verification = PhoneVerificationCode.objects.create(phone='+996700111222', code='4321')
        verification.created_at = timezone.now() - timezone.timedelta(minutes=11)
        verification.save()

        response = self.client.post(self.confirm_url, {
            'phone': '+996700111222',
            'code': '4321',
            'password': 'newpassword123',
            'first_name': 'Jan',
            'last_name': 'Kovalski'
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Срок действия кода истёк', str(response.data))

    def test_jazzmin_paginator_number_monkeypatch(self):
        from jazzmin.templatetags.jazzmin import jazzmin_paginator_number
        
        class MockPaginator:
            num_pages = 5

        class MockChangeList:
            paginator = MockPaginator()
            page_num = 2
            def get_query_string(self, params):
                return f"?p={params.get('p', 1)}"

        cl = MockChangeList()

        try:
            result = jazzmin_paginator_number(cl, 1)
            self.assertIsNotNone(result)
            result_current = jazzmin_paginator_number(cl, 2)
            self.assertIsNotNone(result_current)
        except TypeError as e:
            self.fail(f"jazzmin_paginator_number raised TypeError: {e}")


class EmailRegistrationTests(APITestCase):
    def setUp(self):
        self.request_url = '/api/auth/register/email/request/'
        self.confirm_url = '/api/auth/register/email/confirm/'
        self.login_url = '/api/auth/login/'

    def test_request_code_success(self):
        response = self.client.post(self.request_url, {'email': 'newpatient@example.com'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['detail'], 'Код подтверждения отправлен на указанный email.')

        self.assertTrue(EmailVerificationCode.objects.filter(email='newpatient@example.com').exists())
        verification = EmailVerificationCode.objects.filter(email='newpatient@example.com').first()
        self.assertEqual(len(verification.code), 4)

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(verification.code, mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to, ['newpatient@example.com'])

    def test_request_code_duplicate_email_fails(self):
        User.objects.create_user(
            email='existing@example.com',
            password='password123',
            first_name='Existing',
            last_name='User',
        )

        response = self.client.post(self.request_url, {'email': 'existing@example.com'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)

    def test_confirm_registration_success(self):
        verification = EmailVerificationCode.objects.create(email='newpatient@example.com', code='4321')

        response = self.client.post(self.confirm_url, {
            'email': 'newpatient@example.com',
            'code': '4321',
            'password': 'newpassword123',
            'first_name': 'Jan',
            'last_name': 'Kovalski'
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertEqual(response.data['user']['first_name'], 'Jan')

        verification.refresh_from_db()
        self.assertTrue(verification.is_used)

        user = User.objects.get(email='newpatient@example.com')
        self.assertEqual(user.first_name, 'Jan')
        self.assertEqual(user.role, User.Role.PATIENT)

        login_response = self.client.post(self.login_url, {
            'email': 'newpatient@example.com',
            'password': 'newpassword123'
        })
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        self.assertIn('access', login_response.data)

    def test_confirm_registration_incorrect_code(self):
        EmailVerificationCode.objects.create(email='newpatient@example.com', code='4321')

        response = self.client.post(self.confirm_url, {
            'email': 'newpatient@example.com',
            'code': '0000',
            'password': 'newpassword123',
            'first_name': 'Jan',
            'last_name': 'Kovalski'
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('code', response.data)

    def test_confirm_registration_expired_code(self):
        verification = EmailVerificationCode.objects.create(email='newpatient@example.com', code='4321')
        verification.created_at = timezone.now() - timezone.timedelta(minutes=11)
        verification.save()

        response = self.client.post(self.confirm_url, {
            'email': 'newpatient@example.com',
            'code': '4321',
            'password': 'newpassword123',
            'first_name': 'Jan',
            'last_name': 'Kovalski'
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Срок действия кода истёк', str(response.data))


class LoginOTPTests(APITestCase):
    """Вход по OTP доступен любой роли — не только пациентам."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='otpuser@example.com',
            password='somepassword123',
            first_name='Otp',
            last_name='User',
            phone='+996700333444',
            role=User.Role.DOCTOR,
        )
        self.request_url = '/api/auth/login/otp/request/'
        self.verify_url = '/api/auth/login/otp/verify/'

    def test_request_otp_existing_email(self):
        response = self.client.post(self.request_url, {'email': 'otpuser@example.com'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertTrue(LoginCode.objects.filter(email='otpuser@example.com').exists())
        code_obj = LoginCode.objects.filter(email='otpuser@example.com').first()
        self.assertEqual(len(code_obj.code), 6)

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(code_obj.code, mail.outbox[0].body)

    def test_request_otp_nonexistent_email_no_leak(self):
        response = self.client.post(self.request_url, {'email': 'nobody@example.com'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(LoginCode.objects.filter(email='nobody@example.com').exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_request_otp_existing_phone(self):
        response = self.client.post(self.request_url, {'phone': '+996700333444'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(LoginCode.objects.filter(phone='+996700333444').exists())

    def test_request_otp_requires_email_or_phone(self):
        response = self.client.post(self.request_url, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_otp_success_logs_in(self):
        LoginCode.objects.create(email='otpuser@example.com', code='555555')

        response = self.client.post(self.verify_url, {
            'email': 'otpuser@example.com',
            'code': '555555',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertEqual(response.data['user']['email'], 'otpuser@example.com')

    def test_verify_otp_marks_code_used(self):
        code_obj = LoginCode.objects.create(email='otpuser@example.com', code='555555')

        self.client.post(self.verify_url, {'email': 'otpuser@example.com', 'code': '555555'})
        code_obj.refresh_from_db()
        self.assertTrue(code_obj.is_used)

        # Повторное использование того же кода не проходит
        response = self.client.post(self.verify_url, {'email': 'otpuser@example.com', 'code': '555555'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_otp_incorrect_code(self):
        LoginCode.objects.create(email='otpuser@example.com', code='555555')

        response = self.client.post(self.verify_url, {
            'email': 'otpuser@example.com',
            'code': '000000',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('code', response.data)

    def test_verify_otp_expired_code(self):
        code_obj = LoginCode.objects.create(email='otpuser@example.com', code='555555')
        code_obj.created_at = timezone.now() - timezone.timedelta(minutes=11)
        code_obj.save()

        response = self.client.post(self.verify_url, {
            'email': 'otpuser@example.com',
            'code': '555555',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Срок действия кода истёк', str(response.data))

    def test_verify_otp_by_phone(self):
        LoginCode.objects.create(phone='+996700333444', code='555555')

        response = self.client.post(self.verify_url, {
            'phone': '+996700333444',
            'code': '555555',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)


class VerifyContactTests(APITestCase):
    """/api/auth/verify/*/ — подтверждает владение контактом, но НЕ создаёт аккаунт
    (в отличие от /register/email|phone/confirm/, которые сразу создают пациента)."""

    def test_verify_email_confirm_marks_used_without_creating_account(self):
        verification = EmailVerificationCode.objects.create(email='doc-to-be@example.com', code='1234')

        response = self.client.post('/api/auth/verify/email/confirm/', {
            'email': 'doc-to-be@example.com',
            'code': '1234',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        verification.refresh_from_db()
        self.assertTrue(verification.is_used)
        self.assertFalse(User.objects.filter(email='doc-to-be@example.com').exists())

    def test_verify_phone_confirm_marks_used_without_creating_account(self):
        verification = PhoneVerificationCode.objects.create(phone='+996700555666', code='4321')

        response = self.client.post('/api/auth/verify/phone/confirm/', {
            'phone': '+996700555666',
            'code': '4321',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        verification.refresh_from_db()
        self.assertTrue(verification.is_used)
        self.assertFalse(User.objects.filter(phone='+996700555666').exists())

    def test_verify_email_confirm_wrong_code(self):
        EmailVerificationCode.objects.create(email='doc-to-be@example.com', code='1234')

        response = self.client.post('/api/auth/verify/email/confirm/', {
            'email': 'doc-to-be@example.com',
            'code': '0000',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_email_request_reuses_registration_endpoint(self):
        # /verify/email/request/ и /register/email/request/ — одна и та же вьюха,
        # это намеренное переиспользование (не дублировать код request-шага).
        response = self.client.post('/api/auth/verify/email/request/', {'email': 'newdoctor@example.com'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(EmailVerificationCode.objects.filter(email='newdoctor@example.com').exists())


class DoctorClinicRegistrationVerificationGateTests(APITestCase):
    """Регистрация врача/клиники теперь тоже требует подтверждённый email/телефон —
    как и у пациента, просто не в один шаг с созданием аккаунта (анкета длинная)."""

    def _doctor_payload(self, email, **step1_extra):
        step1 = {'full_name': 'Иван Иванов', 'email': email, **step1_extra}
        return {
            'password': 'doctorpass123',
            'step1': json.dumps(step1),
            'step2': json.dumps({}),
            'step3': json.dumps({}),
            'step4': json.dumps({}),
            'step5': json.dumps({}),
            'step6': json.dumps({}),
            'step7': json.dumps({
                'agree_terms': True, 'agree_privacy': True,
                'agree_data_processing': True, 'agree_publishing': True,
            }),
        }

    def _clinic_payload(self, email, **step2_extra):
        step2 = {'email': email, **step2_extra}
        return {
            'password': 'clinicpass123',
            'step1': json.dumps({'name': 'Клиника Тест'}),
            'step2': json.dumps(step2),
            'step3': json.dumps({}),
            'step4': json.dumps({}),
            'step5': json.dumps({}),
            'step6': json.dumps({}),
            'step7': json.dumps({
                'agree_terms': True, 'agree_privacy': True,
                'agree_data_processing': True, 'agree_publishing': True,
            }),
        }

    def test_doctor_registration_without_verification_fails(self):
        response = self.client.post('/api/auth/register/doctor/', self._doctor_payload('unverified-doc@example.com'))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(email='unverified-doc@example.com').exists())

    def test_doctor_registration_with_verified_email_succeeds(self):
        EmailVerificationCode.objects.create(
            email='verified-doc@example.com', code='1234', is_used=True,
        )
        response = self.client.post('/api/auth/register/doctor/', self._doctor_payload('verified-doc@example.com'))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email='verified-doc@example.com', role=User.Role.DOCTOR).exists())

    def test_doctor_registration_with_verified_phone_succeeds(self):
        PhoneVerificationCode.objects.create(
            phone='+996700777888', code='4321', is_used=True,
        )
        payload = self._doctor_payload('verified-doc-phone@example.com', phone='+996700777888')
        response = self.client.post('/api/auth/register/doctor/', payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_doctor_registration_with_stale_verification_fails(self):
        old_verification = EmailVerificationCode.objects.create(
            email='stale-doc@example.com', code='1234', is_used=True,
        )
        old_verification.created_at = timezone.now() - timezone.timedelta(hours=25)
        old_verification.save()

        response = self.client.post('/api/auth/register/doctor/', self._doctor_payload('stale-doc@example.com'))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_clinic_registration_without_verification_fails(self):
        response = self.client.post('/api/auth/register/clinic/', self._clinic_payload('unverified-clinic@example.com'))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(email='unverified-clinic@example.com').exists())

    def test_clinic_registration_with_verified_email_succeeds(self):
        EmailVerificationCode.objects.create(
            email='verified-clinic@example.com', code='1234', is_used=True,
        )
        response = self.client.post('/api/auth/register/clinic/', self._clinic_payload('verified-clinic@example.com'))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email='verified-clinic@example.com', role=User.Role.CLINIC).exists())

    def test_full_flow_request_then_confirm_then_register(self):
        """Реалистичный сценарий: запросить код → подтвердить → отправить анкету."""
        r1 = self.client.post('/api/auth/verify/email/request/', {'email': 'flow-doc@example.com'})
        self.assertEqual(r1.status_code, status.HTTP_200_OK)

        code = EmailVerificationCode.objects.get(email='flow-doc@example.com').code

        r2 = self.client.post('/api/auth/verify/email/confirm/', {
            'email': 'flow-doc@example.com', 'code': code,
        })
        self.assertEqual(r2.status_code, status.HTTP_200_OK)

        r3 = self.client.post('/api/auth/register/doctor/', self._doctor_payload('flow-doc@example.com'))
        self.assertEqual(r3.status_code, status.HTTP_201_CREATED)
        self.assertIn('access', r3.data)


