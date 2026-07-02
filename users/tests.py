from django.core import mail
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from users.models import PasswordResetCode

User = get_user_model()

class PasswordResetTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='oldpassword123',
            first_name='Test',
            last_name='User'
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
