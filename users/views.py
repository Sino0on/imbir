from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer, OpenApiParameter
from rest_framework import serializers, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.exceptions import TokenError

import random
from .models import (
    DoctorDocument, ClinicPhoto, ClinicDocument, PasswordResetCode, PhoneVerificationCode,
    EmailVerificationCode, LoginCode, DoctorClinicLink,
)
from clinics.serializers import ClinicListSerializer, ClinicBranchSerializer
from .serializers import (
    LoginSerializer, UserMeSerializer,
    ClientRegisterSerializer, DoctorRegisterSerializer, ClinicRegisterSerializer,
    PasswordResetVerifySerializer, PasswordResetConfirmSerializer,
    PhoneRegisterRequestSerializer, PhoneRegisterConfirmSerializer,
    EmailRegisterRequestSerializer, EmailRegisterConfirmSerializer,
    LoginOTPRequestSerializer, LoginOTPVerifySerializer,
    VerifyEmailConfirmSerializer, VerifyPhoneConfirmSerializer,
    EmailCheckSerializer, PhoneCheckSerializer, InviteAcceptSerializer,
    resolve_clinic_invite,
)
from users.utils import (
    link_guest_appointments, make_phone_placeholder_email,
    save_hybrid_documents, send_sms_nikita, send_telegram_debug,
)

_TOKEN_RESPONSE = inline_serializer('TokenResponse', fields={
    'access': serializers.CharField(),
    'refresh': serializers.CharField(),
    'user': UserMeSerializer(),
})


@extend_schema(request=LoginSerializer, responses={200: _TOKEN_RESPONSE}, tags=['auth'])
class LoginView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserMeSerializer(user).data,
        })


@extend_schema(
    request=inline_serializer('LogoutRequest', fields={'refresh': serializers.CharField()}),
    responses={204: None},
    tags=['auth'],
)
class LogoutView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({'detail': 'refresh токен обязателен'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            return Response({'detail': 'Неверный или просроченный токен'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(request=ClientRegisterSerializer, responses={201: _TOKEN_RESPONSE}, tags=['auth'])
class ClientRegisterView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = ClientRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserMeSerializer(user).data,
        }, status=status.HTTP_201_CREATED)


@extend_schema(request=DoctorRegisterSerializer, responses={201: _TOKEN_RESPONSE}, tags=['auth'])
class DoctorRegisterView(APIView):
    permission_classes = (AllowAny,)
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def post(self, request):
        process_photo = str(request.data.get('process_photo', '')).strip().lower() in ('1', 'true', 'yes')
        uploaded_photo = request.FILES.get('photo')

        serializer = DoctorRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        doctor_profile = user.doctor_profile
        save_hybrid_documents(doctor_profile, 'documents', DoctorDocument, request)

        # ИИ-обработка фото — в фоне (см. doctor/tasks.py). Раньше она шла прямо
        # здесь, около минуты: клиент с таймаутом 15 с видел «Ошибка регистрации»
        # при уже созданном аккаунте, а повтор упирался в «email уже существует».
        photo_ai_processing = None
        if process_photo and uploaded_photo and doctor_profile.photo:
            from doctor.tasks import queue_doctor_photo_processing
            from references.models import SiteSettings
            if not SiteSettings.load().ai_doctor_photo_processing_enabled:
                photo_ai_processing = 'disabled'
            elif queue_doctor_photo_processing(doctor_profile):
                photo_ai_processing = 'queued'
            else:
                photo_ai_processing = 'failed'

        refresh = RefreshToken.for_user(user)
        response_data = {
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserMeSerializer(user).data,
        }
        if photo_ai_processing:
            response_data['photo_ai_processing'] = photo_ai_processing
        return Response(response_data, status=status.HTTP_201_CREATED)


@extend_schema(request=ClinicRegisterSerializer, responses={201: _TOKEN_RESPONSE}, tags=['auth'])
class ClinicRegisterView(APIView):
    permission_classes = (AllowAny,)
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def post(self, request):
        serializer = ClinicRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        clinic_profile = user.clinic_profile
        save_hybrid_documents(clinic_profile, 'photos', ClinicPhoto, request)
        save_hybrid_documents(clinic_profile, 'documents', ClinicDocument, request)

        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserMeSerializer(user).data,
        }, status=status.HTTP_201_CREATED)


@extend_schema_view(
    get=extend_schema(responses={200: UserMeSerializer}, tags=['auth']),
    put=extend_schema(request=UserMeSerializer, responses={200: UserMeSerializer}, tags=['auth']),
)
class MeView(APIView):
    permission_classes = (IsAuthenticated,)
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def get(self, request):
        return Response(UserMeSerializer(request.user, context={'request': request}).data)

    def put(self, request):
        serializer = UserMeSerializer(request.user, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


from django.core import signing
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import get_user_model

User = get_user_model()


@extend_schema(
    request=inline_serializer('PasswordResetRequest', fields={
        'email': serializers.EmailField(required=False),
        'phone': serializers.CharField(required=False),
    }),
    responses={200: inline_serializer('PasswordResetRequestSuccess', fields={'detail': serializers.CharField()})},
    tags=['auth'],
)
class PasswordResetRequestView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        email = request.data.get('email', '').strip()
        phone = request.data.get('phone', '').strip()

        if not email and not phone:
            return Response({'error': 'Email или телефон обязательны'}, status=status.HTTP_400_BAD_REQUEST)

        code = f"{random.randint(100000, 999999)}"

        if email:
            try:
                user = User.objects.get(email__iexact=email)
                PasswordResetCode.objects.create(email=email, code=code)

                subject = "Восстановление пароля — Imbir"
                message = (
                    f"Здравствуйте!\n\n"
                    f"Вы получили это письмо, потому что запросили сброс пароля.\n"
                    f"Код подтверждения для сброса пароля:\n\n"
                    f"{code}\n\n"
                    f"Если вы не запрашивали сброс пароля, проигнорируйте это письмо.\n"
                )
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL or 'noreply@imbir.kg',
                    [user.email],
                    fail_silently=True,
                )
                send_telegram_debug(f"[Сброс пароля] email={email} код={code}")
            except User.DoesNotExist:
                pass
            return Response({'detail': 'Если пользователь существует, письмо с кодом подтверждения отправлено.'}, status=status.HTTP_200_OK)
        else:
            try:
                user = User.objects.get(phone=phone)
                PasswordResetCode.objects.create(phone=phone, code=code)

                message = f"Код подтверждения для сброса пароля в Imbir: {code}"
                send_sms_nikita(phone, message)
                send_telegram_debug(f"[Сброс пароля] phone={phone} код={code}")
            except User.DoesNotExist:
                pass
            return Response({'detail': 'Если пользователь существует, СМС с кодом подтверждения отправлено.'}, status=status.HTTP_200_OK)


@extend_schema(
    request=PasswordResetVerifySerializer,
    responses={200: inline_serializer('PasswordResetVerifySuccess', fields={'detail': serializers.CharField()})},
    tags=['auth'],
)
class PasswordResetVerifyView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = PasswordResetVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({'detail': 'Код подтверждён успешно.'}, status=status.HTTP_200_OK)


@extend_schema(
    request=PasswordResetConfirmSerializer,
    responses={200: inline_serializer('PasswordResetConfirmSuccess', fields={'detail': serializers.CharField()})},
    tags=['auth'],
)
class PasswordResetConfirmView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data.get('email')
        phone = serializer.validated_data.get('phone')
        password = serializer.validated_data['password']
        reset_code = serializer.validated_data['reset_code']

        try:
            if email:
                user = User.objects.get(email__iexact=email)
            else:
                user = User.objects.get(phone=phone)
            user.set_password(password)
            user.save()

            reset_code.is_used = True
            reset_code.save()
        except User.DoesNotExist:
            return Response({'error': 'Пользователь не найден'}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'detail': 'Пароль успешно сброшен'}, status=status.HTTP_200_OK)


@extend_schema(
    request=PhoneRegisterRequestSerializer,
    responses={200: inline_serializer('PhoneRegisterRequestSuccess', fields={'detail': serializers.CharField()})},
    tags=['auth'],
)
class PhoneRegisterRequestView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = PhoneRegisterRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data['phone']

        # Generate 4-digit code
        code = f"{random.randint(1000, 9999)}"
        PhoneVerificationCode.objects.create(phone=phone, code=code)

        # Send SMS via Nikita
        message = f"Код подтверждения для регистрации в Imbir: {code}"
        send_sms_nikita(phone, message)
        send_telegram_debug(f"[Регистрация, телефон] phone={phone} код={code}")

        return Response({'detail': 'Код подтверждения отправлен на указанный номер телефона.'}, status=status.HTTP_200_OK)


@extend_schema(
    request=PhoneRegisterConfirmSerializer,
    responses={201: _TOKEN_RESPONSE},
    tags=['auth'],
)
class PhoneRegisterConfirmView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = PhoneRegisterConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone = serializer.validated_data['phone']
        password = serializer.validated_data['password']
        first_name = serializer.validated_data['first_name']
        last_name = serializer.validated_data['last_name']
        verification = serializer.validated_data['verification']

        # Технический email по цифрам номера. Если такая заглушка уже занята
        # (прежний владелец номера сменил телефон), берётся свободный вариант.
        placeholder_email = make_phone_placeholder_email(phone)

        # Create user
        user = User.objects.create_user(
            email=placeholder_email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            role=User.Role.PATIENT
        )

        # Mark code as used
        verification.is_used = True
        verification.save()

        # Номер подтверждён кодом — забираем гостевые записи, сделанные на него
        # до регистрации, чтобы они появились в «Истории записей».
        link_guest_appointments(user, phone=phone)

        # Login immediately and return tokens
        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserMeSerializer(user, context={'request': request}).data,
        }, status=status.HTTP_201_CREATED)


@extend_schema(
    request=EmailRegisterRequestSerializer,
    responses={200: inline_serializer('EmailRegisterRequestSuccess', fields={'detail': serializers.CharField()})},
    tags=['auth'],
)
class EmailRegisterRequestView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = EmailRegisterRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']

        # Generate 4-digit code
        code = f"{random.randint(1000, 9999)}"
        EmailVerificationCode.objects.create(email=email, code=code)

        subject = "Код подтверждения — Imbir"
        message = f"Код подтверждения для регистрации в Imbir: {code}"
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL or 'noreply@imbir.kg', [email], fail_silently=True)
        send_telegram_debug(f"[Регистрация, email] email={email} код={code}")

        return Response({'detail': 'Код подтверждения отправлен на указанный email.'}, status=status.HTTP_200_OK)


@extend_schema(
    request=EmailRegisterConfirmSerializer,
    responses={201: _TOKEN_RESPONSE},
    tags=['auth'],
)
class EmailRegisterConfirmView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = EmailRegisterConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']
        password = serializer.validated_data['password']
        first_name = serializer.validated_data['first_name']
        last_name = serializer.validated_data['last_name']
        verification = serializer.validated_data['verification']

        user = User.objects.create_user(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            role=User.Role.PATIENT,
        )

        verification.is_used = True
        verification.save()

        # Email подтверждён кодом — привязываем гостевые записи на этот адрес.
        link_guest_appointments(user, email=email)

        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserMeSerializer(user, context={'request': request}).data,
        }, status=status.HTTP_201_CREATED)


@extend_schema(
    request=LoginOTPRequestSerializer,
    responses={200: inline_serializer('LoginOTPRequestSuccess', fields={'detail': serializers.CharField()})},
    tags=['auth'],
)
class LoginOTPRequestView(APIView):
    """Запросить код входа без пароля — доступно любой существующей роли."""
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = LoginOTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        phone = serializer.validated_data['phone']

        code = f"{random.randint(100000, 999999)}"

        if email:
            user = User.objects.filter(email__iexact=email).first()
            if user:
                LoginCode.objects.create(email=email, code=code)
                subject = "Код входа — Imbir"
                message = f"Код подтверждения для входа в Imbir: {code}"
                send_mail(subject, message, settings.DEFAULT_FROM_EMAIL or 'noreply@imbir.kg', [email], fail_silently=True)
                send_telegram_debug(f"[Вход] email={email} код={code}")
            return Response(
                {'detail': 'Если пользователь существует, письмо с кодом входа отправлено.'},
                status=status.HTTP_200_OK,
            )

        user = User.objects.filter(phone=phone).first()
        if user:
            LoginCode.objects.create(phone=phone, code=code)
            message = f"Код подтверждения для входа в Imbir: {code}"
            send_sms_nikita(phone, message)
            send_telegram_debug(f"[Вход] phone={phone} код={code}")
        return Response(
            {'detail': 'Если пользователь существует, СМС с кодом входа отправлено.'},
            status=status.HTTP_200_OK,
        )


@extend_schema(request=LoginOTPVerifySerializer, responses={200: _TOKEN_RESPONSE}, tags=['auth'])
class LoginOTPVerifyView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = LoginOTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']

        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserMeSerializer(user, context={'request': request}).data,
        })


@extend_schema(
    request=VerifyEmailConfirmSerializer,
    responses={200: inline_serializer('VerifyEmailConfirmSuccess', fields={'detail': serializers.CharField()})},
    tags=['auth'],
    summary='Подтвердить email кодом перед регистрацией врача/клиники (аккаунт не создаётся)',
)
class VerifyEmailConfirmView(APIView):
    """Подтверждение email без создания аккаунта — шаг перед многошаговой
    регистрацией врача/клиники. Код запрашивается через EmailRegisterRequestView
    (тот же /api/auth/verify/email/request/ = /api/auth/register/email/request/)."""
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = VerifyEmailConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        verification = serializer.validated_data['verification']
        verification.is_used = True
        verification.save(update_fields=['is_used'])

        return Response({'detail': 'Email подтверждён.'}, status=status.HTTP_200_OK)


@extend_schema(
    request=VerifyPhoneConfirmSerializer,
    responses={200: inline_serializer('VerifyPhoneConfirmSuccess', fields={'detail': serializers.CharField()})},
    tags=['auth'],
    summary='Подтвердить телефон кодом перед регистрацией врача/клиники (аккаунт не создаётся)',
)
class VerifyPhoneConfirmView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = VerifyPhoneConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        verification = serializer.validated_data['verification']
        verification.is_used = True
        verification.save(update_fields=['is_used'])

        return Response({'detail': 'Телефон подтверждён.'}, status=status.HTTP_200_OK)


_INVITE_VALIDATE_RESPONSE = inline_serializer('InviteValidateResponse', fields={
    'data': inline_serializer('InviteValidateData', fields={
        'valid': serializers.BooleanField(),
        'invite_id': serializers.UUIDField(allow_null=True),
        'clinic': ClinicListSerializer(allow_null=True),
        'branch': ClinicBranchSerializer(allow_null=True),
    }),
})


def _invite_lookup_params(source):
    """Параметры ссылки-приглашения из query/body: invite (uuid инвайта) или
    старые invite_clinic_id/invite_branch_id. Мусор вместо uuid/числа — как
    отсутствие параметра: битая ссылка даёт «недействительно», а не 500."""
    import uuid

    def _positive_int(value):
        try:
            value = int(str(value).strip())
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None

    invite_id = str(source.get('invite') or '').strip()
    try:
        invite_id = uuid.UUID(invite_id) if invite_id else None
    except ValueError:
        invite_id = None
    return {
        'invite_id': invite_id,
        'clinic_user_id': _positive_int(source.get('invite_clinic_id')),
        'branch_id': _positive_int(source.get('invite_branch_id')),
    }


@extend_schema(
    parameters=[
        OpenApiParameter(
            name='invite', type=str, location=OpenApiParameter.QUERY, required=False,
            description='id инвайта (uuid) из ссылки /register/doctor?invite=… — проверяется '
                        'ровно этот инвайт. Если передан, invite_clinic_id не нужен.',
        ),
        OpenApiParameter(
            name='invite_clinic_id', type=int, location=OpenApiParameter.QUERY, required=False,
            description='Старый формат ссылки: user_id клиники — то же значение, что потом '
                        'уходит в /register/doctor/. Обязателен, если не передан invite.',
        ),
        OpenApiParameter(
            name='invite_branch_id', type=int, location=OpenApiParameter.QUERY, required=False,
            description='Старый формат ссылки: id филиала (без него — главный офис).',
        ),
    ],
    responses={200: _INVITE_VALIDATE_RESPONSE},
    tags=['auth'],
    summary='Проверить пригласительную ссылку клиники до начала регистрации врача',
    description=(
        'Публичный эндпоинт для welcome-экрана перед 7-шаговой анкетой врача: показывает, '
        'действителен ли инвайт, и карточку клиники (+ филиала), не дожидаясь финальной '
        'отправки формы. Логика поиска инвайта та же, что и в самой регистрации — '
        'валидность не гарантирует, что она не изменится к моменту сабмита (клиника может '
        'отозвать инвайт), финальная проверка всё равно происходит на /register/doctor/.'
    ),
)
class InviteValidateView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        if (
            not request.query_params.get('invite', '').strip()
            and not request.query_params.get('invite_clinic_id', '').strip()
        ):
            return Response(
                {'detail': 'Параметр invite_clinic_id обязателен.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        params = _invite_lookup_params(request.query_params)
        invite = None
        if params['invite_id'] or params['clinic_user_id']:
            invite, _error = resolve_clinic_invite(**params)

        if invite is None:
            return Response({'data': {'valid': False, 'invite_id': None, 'clinic': None, 'branch': None}})

        return Response({'data': {
            'valid': True,
            'invite_id': str(invite.pk),
            'clinic': ClinicListSerializer(invite.clinic, context={'request': request}).data,
            'branch': ClinicBranchSerializer(invite.branch).data if invite.branch else None,
        }})


@extend_schema(
    request=InviteAcceptSerializer,
    responses={200: inline_serializer('InviteAcceptResponse', fields={
        'data': inline_serializer('InviteAcceptData', fields={
            'already_linked': serializers.BooleanField(),
            'clinic': ClinicListSerializer(),
            'branch': ClinicBranchSerializer(allow_null=True),
        }),
    })},
    tags=['auth'],
    summary='Принять ссылку-приглашение клиники уже зарегистрированным врачом',
    description=(
        'Врач с аккаунтом не может пройти регистрацию по ссылке повторно («email уже '
        'используется»). Эндпоинт создаёт связь врача с клиникой (или восстанавливает '
        'отключённую) с филиалом из инвайта. Если врач уже работает в клинике, связь не '
        'меняется — already_linked=true.'
    ),
)
class InviteAcceptView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        from users.models import DoctorProfile

        doctor = None
        if request.user.role == User.Role.DOCTOR:
            doctor = DoctorProfile.objects.filter(user=request.user).first()
        if doctor is None:
            return Response(
                {'detail': 'Принять приглашение клиники может только врач.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = InviteAcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        invite, error = resolve_clinic_invite(
            invite_id=data.get('invite'),
            clinic_user_id=data.get('invite_clinic_id'),
            branch_id=data.get('invite_branch_id'),
        )
        if error:
            return Response(
                {'invite' if data.get('invite') else 'invite_clinic_id': [error]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        link, created = DoctorClinicLink.objects.get_or_create(
            doctor=doctor, clinic=invite.clinic,
            defaults={'branch': invite.branch, 'is_active': True},
        )
        already_linked = not created and link.is_active
        if not created and not link.is_active:
            # Отвязанного раньше врача возвращаем — с филиалом из нового инвайта.
            link.is_active = True
            link.branch = invite.branch
            link.save(update_fields=['is_active', 'branch'])

        return Response({'data': {
            'already_linked': already_linked,
            'clinic': ClinicListSerializer(invite.clinic, context={'request': request}).data,
            'branch': ClinicBranchSerializer(invite.branch).data if invite.branch else None,
        }})


@extend_schema(
    request=EmailCheckSerializer,
    responses={200: inline_serializer('EmailAvailabilityResponse', fields={
        'data': inline_serializer('EmailAvailabilityData', fields={
            'email': serializers.EmailField(),
            'available': serializers.BooleanField(),
        }),
    })},
    tags=['auth'],
    summary='Проверка занятости email',
    description='Свободен ли email для регистрации — без отправки кода и без побочных эффектов.',
)
class EmailAvailabilityView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = EmailCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']

        available = not User.objects.filter(email__iexact=email).exists()
        return Response({'data': {'email': email, 'available': available}})


_PHONE_AVAILABILITY_RESPONSE = inline_serializer('PhoneAvailabilityResponse', fields={
    'data': inline_serializer('PhoneAvailabilityData', fields={
        'phone': serializers.CharField(),
        'available': serializers.BooleanField(),
    }),
})


@extend_schema_view(
    get=extend_schema(
        parameters=[OpenApiParameter(
            name='phone', type=str, location=OpenApiParameter.QUERY, required=True,
            description='Номер с кодом страны, как он уйдёт в регистрацию: +996700000001.',
        )],
        responses={200: _PHONE_AVAILABILITY_RESPONSE},
        tags=['auth'],
        summary='Проверка занятости телефона',
        description='Свободен ли телефон для регистрации врача/клиники — без отправки кода '
                    'и без побочных эффектов. Пара к /api/auth/email/check/.',
    ),
    post=extend_schema(
        request=PhoneCheckSerializer,
        responses={200: _PHONE_AVAILABILITY_RESPONSE},
        tags=['auth'],
        summary='Проверка занятости телефона',
    ),
)
class PhoneAvailabilityView(APIView):
    permission_classes = (AllowAny,)

    def _check(self, data):
        serializer = PhoneCheckSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data['phone']
        # Та же проверка, что в DoctorRegisterSerializer/ClinicRegisterSerializer —
        # иначе о занятом номере врач/клиника узнают только после всех шагов анкеты.
        available = not User.objects.filter(phone=phone).exists()
        return Response({'data': {'phone': phone, 'available': available}})

    def get(self, request):
        return self._check({'phone': request.query_params.get('phone', '')})

    def post(self, request):
        return self._check(request.data)



