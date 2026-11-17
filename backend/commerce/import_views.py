from django.db import transaction
from django.http import HttpResponse
from django.urls import path
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.generics import get_object_or_404

from .imports import ImportProblem, stage_upload, template_csv
from .models import ImportBatch, OutboxEvent
from .permissions import IsOperator


CanImport = IsOperator


class BatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportBatch
        fields = ["id", "kind", "status", "filename", "source_name", "progress", "total_rows", "valid_rows",
                  "error_rows", "errors", "preview", "result", "created_at", "committed_at"]


class BatchListSerializer(serializers.Serializer):
    results = BatchSerializer(many=True)


class UploadSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["catalog", "opening_stock", "adjustments", "history"])
    source_name = serializers.CharField()
    file = serializers.FileField(required=False)
    files = serializers.ListField(child=serializers.FileField(), required=False)


def _wake_worker():
    from .tasks import deliver_outbox
    try:
        deliver_outbox.delay()
    except Exception:
        # The durable event stays pending and Celery beat will retry delivery.
        pass


def _schedule(kind, batch):
    OutboxEvent.objects.create(kind=kind, payload={"batch_id": str(batch.id)})
    transaction.on_commit(_wake_worker)


@extend_schema(operation_id="imports_list", methods=["GET"], responses=BatchListSerializer, tags=["Imports"])
@extend_schema(operation_id="imports_upload", methods=["POST"], request={"multipart/form-data": UploadSerializer}, responses={202: BatchSerializer}, tags=["Imports"])
@api_view(["GET", "POST"])
@permission_classes([CanImport])
def batches(request):
    if request.method == "GET":
        return Response({"results": BatchSerializer(ImportBatch.objects.order_by("-created_at")[:100], many=True).data})
    files = request.FILES.getlist("files") or request.FILES.getlist("file")
    try:
        with transaction.atomic():
            batch = stage_upload(kind=request.data.get("kind", ""), source_name=request.data.get("source_name", ""), files=files, actor=request.user)
            _schedule("import_validate", batch)
    except ImportProblem as exc:
        raise ValidationError(str(exc)) from exc
    return Response(BatchSerializer(batch).data, status=202)


@extend_schema(operation_id="imports_detail", responses=BatchSerializer, tags=["Imports"])
@api_view(["GET"])
@permission_classes([CanImport])
def batch_detail(request, batch_id):
    return Response(BatchSerializer(get_object_or_404(ImportBatch, pk=batch_id)).data)


@extend_schema(operation_id="imports_commit", request=None, responses={200: BatchSerializer, 202: BatchSerializer}, tags=["Imports"])
@api_view(["POST"])
@permission_classes([CanImport])
def commit(request, batch_id):
    with transaction.atomic():
        batch = get_object_or_404(ImportBatch.objects.select_for_update(), pk=batch_id)
        if batch.status == "completed":
            return Response(BatchSerializer(batch).data)
        if batch.status == "committing":
            return Response(BatchSerializer(batch).data, status=202)
        if batch.status != "ready" or batch.error_rows:
            raise ValidationError("Only a validated ready batch with no errors may commit.")
        batch.status = "committing"
        batch.progress = 0
        batch.save(update_fields=["status", "progress"])
        _schedule("import_commit", batch)
    return Response(BatchSerializer(batch).data, status=202)


@extend_schema(operation_id="imports_template", parameters=[OpenApiParameter("kind", OpenApiTypes.STR, enum=["catalog", "opening_stock", "adjustments", "history", "orders", "lines", "shipments", "returns", "refunds", "payments"])],
               responses={(200, "text/csv"): OpenApiResponse(OpenApiTypes.STR, description="CSV header template.")}, tags=["Imports"])
@api_view(["GET"])
@permission_classes([CanImport])
def templates(request):
    kind = request.query_params.get("kind", "catalog")
    try:
        content = template_csv(kind)
    except ImportProblem as exc:
        raise ValidationError(str(exc)) from exc
    response = HttpResponse(content, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{kind}.csv"'
    return response


urlpatterns = [path("", batches), path("templates/", templates), path("<uuid:batch_id>/", batch_detail), path("<uuid:batch_id>/commit/", commit)]
