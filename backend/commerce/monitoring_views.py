from rest_framework import serializers
from rest_framework.decorators import api_view,permission_classes
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from .monitoring import operations_health
from .permissions import IsOperator

class OperationsCountsSerializer(serializers.Serializer):
    overdue_cod_orders=serializers.IntegerField()
    failed_outbox_jobs=serializers.IntegerField()
    failed_imports=serializers.IntegerField()
    payment_exceptions=serializers.IntegerField()

class OverdueCODSerializer(serializers.Serializer):
    id=serializers.UUIDField();number=serializers.CharField();status=serializers.CharField()
    created_at=serializers.DateTimeField();confirmed_at=serializers.DateTimeField(allow_null=True)
    age_hours=serializers.FloatField()

class ExhaustedOutboxSerializer(serializers.Serializer):
    id=serializers.UUIDField();kind=serializers.CharField();attempts=serializers.IntegerField()

class FailedImportSerializer(serializers.Serializer):
    id=serializers.UUIDField();kind=serializers.CharField();status=serializers.CharField();created_at=serializers.DateTimeField()

class PaymentExceptionSerializer(serializers.Serializer):
    id=serializers.UUIDField();number=serializers.CharField()
    unreconciled_amount=serializers.DecimalField(max_digits=14,decimal_places=2)

class OperationsHealthSerializer(serializers.Serializer):
    status=serializers.ChoiceField(choices=['ok','attention']);checked_at=serializers.DateTimeField()
    counts=OperationsCountsSerializer();overdue_cod_orders=OverdueCODSerializer(many=True)
    failed_outbox_jobs=ExhaustedOutboxSerializer(many=True);failed_imports=FailedImportSerializer(many=True)
    payment_exceptions=PaymentExceptionSerializer(many=True);sample_limit=serializers.IntegerField()

@extend_schema(operation_id='staff_operations_health_get',responses=OperationsHealthSerializer,tags=['Staff'],description='Uncached, redacted attention signals. Attention still returns HTTP200; the management check exits nonzero for monitors.')
@api_view(['GET'])
@permission_classes([IsOperator])
def operations_health_view(request):
    response=Response(operations_health())
    response['Cache-Control']='private, no-store'
    return response
