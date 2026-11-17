from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler
from django.db import IntegrityError

def exception_handler(exc, context):
    if isinstance(exc, IntegrityError):
        return Response({'detail':'This operation conflicts with existing records or a data integrity rule.'},status=409)
    if isinstance(exc, DjangoValidationError):
        return Response({'detail':'Validation failed.','errors':exc.messages},status=400)
    return drf_exception_handler(exc,context)
