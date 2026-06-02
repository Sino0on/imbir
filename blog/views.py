from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.pagination import StandardPagination
from .models import BlogCategory, BlogPost
from .serializers import BlogCategorySerializer, BlogPostDetailSerializer, BlogPostListSerializer


@extend_schema_view(
    get=extend_schema(tags=['Blog']),
)
class BlogPostListView(ListAPIView):
    permission_classes = (AllowAny,)
    serializer_class = BlogPostListSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        qs = BlogPost.objects.filter(is_published=True).select_related('category')

        category = self.request.query_params.get('category', '').strip()
        if category:
            qs = qs.filter(category__slug=category)

        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(title__icontains=search)

        return qs


@extend_schema(tags=['Blog'])
class BlogPostDetailView(RetrieveAPIView):
    permission_classes = (AllowAny,)
    serializer_class = BlogPostDetailSerializer
    lookup_field = 'slug'
    queryset = BlogPost.objects.filter(is_published=True).select_related('category')


@extend_schema(responses={200: BlogCategorySerializer(many=True)}, tags=['Blog'])
class BlogCategoryListView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        categories = BlogCategory.objects.all()
        return Response(BlogCategorySerializer(categories, many=True).data)
