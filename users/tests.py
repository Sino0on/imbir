from django.core import mail
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from users.models import PasswordResetCode, PhoneVerificationCode

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


