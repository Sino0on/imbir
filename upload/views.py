import os
import uuid

from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.conf import settings
from django.core.files.storage import default_storage


@extend_schema(
    request=inline_serializer('UploadRequest', fields={'file': serializers.FileField()}),
    responses={200: inline_serializer('UploadResponse', fields={'url': serializers.CharField()})},
    tags=['Upload'],
)
class FileUploadView(APIView):
    permission_classes = (IsAuthenticated,)
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'Поле file обязательно'}, status=status.HTTP_400_BAD_REQUEST)

        ext = os.path.splitext(file.name)[1].lower()
        filename = f'uploads/{uuid.uuid4().hex}{ext}'
        saved_path = default_storage.save(filename, file)
        url = request.build_absolute_uri(settings.MEDIA_URL + saved_path)
        return Response({'url': url})
