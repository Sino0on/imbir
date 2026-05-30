import math
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        total = self.page.paginator.count
        page_size = self.get_page_size(self.request)
        return Response({
            'data': data,
            'pagination': {
                'page': self.page.number,
                'page_size': page_size,
                'total': total,
                'total_pages': math.ceil(total / page_size) if page_size else 1,
            },
        })

    def get_paginated_response_schema(self, schema):
        return {
            'type': 'object',
            'properties': {
                'data': schema,
                'pagination': {
                    'type': 'object',
                    'properties': {
                        'page': {'type': 'integer'},
                        'page_size': {'type': 'integer'},
                        'total': {'type': 'integer'},
                        'total_pages': {'type': 'integer'},
                    },
                },
            },
        }
