import os
from urllib.parse import urlparse
from django.conf import settings

def get_relative_path_from_url(url):
    """
    Strips settings.MEDIA_URL prefix from absolute/relative media URLs to 
    get the relative path to be stored directly in a FileField/ImageField.
    """
    if not url:
        return None
    try:
        parsed_url = urlparse(url)
        path = parsed_url.path
        media_url = settings.MEDIA_URL  # e.g., '/media/'
        if path.startswith(media_url):
            return path[len(media_url):].lstrip('/')
        if path.startswith('media/'):
            return path[len('media/'):].lstrip('/')
        return path.lstrip('/')
    except Exception:
        return url

def save_hybrid_documents(profile, field_name, model_class, request):
    """
    Saves documents/photos for a profile (DoctorProfile or ClinicProfile).
    Supports:
      1. request.FILES (file uploads)
      2. request.data (string URLs or list of string URLs)
    """
    # 1. Handle file uploads from request.FILES
    for uploaded_file in request.FILES.getlist(field_name):
        if field_name == 'photos':
            model_class.objects.create(clinic=profile, image=uploaded_file)
        elif field_name == 'documents':
            if hasattr(model_class, 'doctor'):
                model_class.objects.create(doctor=profile, file=uploaded_file)
            else:
                model_class.objects.create(clinic=profile, file=uploaded_file)

    # 2. Handle URLs from request.data
    urls_data = []
    if hasattr(request.data, 'getlist'):
        urls_data = request.data.getlist(field_name)
    else:
        urls_data = request.data.get(field_name)

    if urls_data:
        # If it is a string (e.g. JSON string of a list, or comma-separated list), parse/clean it
        if isinstance(urls_data, str):
            urls_data = urls_data.strip()
            if urls_data.startswith('[') and urls_data.endswith(']'):
                import json
                try:
                    urls_data = json.loads(urls_data)
                except ValueError:
                    urls_data = [u.strip() for u in urls_data.split(',') if u.strip()]
            else:
                urls_data = [u.strip() for u in urls_data.split(',') if u.strip()]
        elif not isinstance(urls_data, list):
            urls_data = [urls_data]

        for url in urls_data:
            if not isinstance(url, str) or not url.strip():
                continue
            rel_path = get_relative_path_from_url(url)
            if rel_path:
                if field_name == 'photos':
                    if not model_class.objects.filter(clinic=profile, image=rel_path).exists():
                        model_class.objects.create(clinic=profile, image=rel_path)
                elif field_name == 'documents':
                    if hasattr(model_class, 'doctor'):
                        if not model_class.objects.filter(doctor=profile, file=rel_path).exists():
                            model_class.objects.create(doctor=profile, file=rel_path)
                    else:
                        if not model_class.objects.filter(clinic=profile, file=rel_path).exists():
                            model_class.objects.create(clinic=profile, file=rel_path)
