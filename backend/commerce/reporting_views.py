import csv
import io
from uuid import UUID

from django.http import HttpResponse
from django.urls import path
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .reporting import analytics, drilldown, filters_from_params, variant_analytics
from .reporting_cache import cached_overview
from .permissions import IsStaffReader


class ReportingSummary(serializers.Serializer):
    orders = serializers.IntegerField()
    ordered_units = serializers.IntegerField()
    cancelled_units = serializers.IntegerField()
    ordered_value = serializers.CharField()
    delivered_units = serializers.IntegerField()
    delivered_value = serializers.CharField()
    returned_units = serializers.IntegerField()
    returned_value = serializers.CharField()
    refunded_amount = serializers.CharField()
    net_delivered_value = serializers.CharField()


class ReportingCohort(serializers.Serializer):
    delivered_units = serializers.IntegerField()
    returned_units = serializers.IntegerField()
    return_rate = serializers.FloatField(allow_null=True)
    open_window_units = serializers.IntegerField()
    unresolved_cases = serializers.IntegerField()
    preliminary = serializers.BooleanField()
    as_of = serializers.DateTimeField()
    basis = serializers.CharField()


class ReportingCash(serializers.Serializer):
    scope = serializers.CharField()
    product_filter_applied = serializers.BooleanField()
    collected_amount = serializers.CharField()
    cod_collected_amount = serializers.CharField()
    online_collected_amount = serializers.CharField()
    settled_amount = serializers.CharField()
    refunded_amount = serializers.CharField()
    exception_collected_amount = serializers.CharField()
    sandbox_collected_amount = serializers.CharField()
    basis = serializers.CharField()


class ReportingDelivery(serializers.Serializer):
    delivered_shipments = serializers.IntegerField()
    failed_shipments = serializers.IntegerField()
    returned_to_origin_shipments = serializers.IntegerField()
    terminal_shipments = serializers.IntegerField()
    success_rate = serializers.FloatField(allow_null=True)
    basis = serializers.CharField()


class ReportingTrend(ReportingSummary):
    date = serializers.DateField()


class ReportingProduct(ReportingSummary):
    id = serializers.UUIDField(allow_null=True)
    name = serializers.CharField()
    category = serializers.CharField()
    image_url = serializers.CharField()


class ReportingFilters(serializers.Serializer):
    start = serializers.DateField()
    end = serializers.DateField()
    timezone = serializers.CharField()
    currency = serializers.CharField()
    product_ids = serializers.ListField(child=serializers.UUIDField())


class ReportingComparison(serializers.Serializer):
    start = serializers.DateField()
    end = serializers.DateField()
    summary = ReportingSummary()
    change_percent = serializers.DictField(child=serializers.FloatField(allow_null=True))


class ReportingMeta(serializers.Serializer):
    generated_at = serializers.DateTimeField()
    customer_data = serializers.CharField()
    basis = serializers.CharField()
    money_basis = serializers.CharField()
    cancellation_basis = serializers.CharField()


class ReturnReason(serializers.Serializer):
    reason = serializers.CharField()
    units = serializers.IntegerField()
    count = serializers.IntegerField(allow_null=True)


class ReportingCoverage(serializers.Serializer):
    missing_order_date_units = serializers.IntegerField()
    missing_delivery_date_units = serializers.IntegerField()
    missing_return_date_units = serializers.IntegerField()
    cancelled_units_without_dated_event = serializers.IntegerField()
    undated_collection_amount = serializers.CharField()
    undated_settlement_amount = serializers.CharField()
    basis = serializers.CharField()


class AnalyticsResponse(serializers.Serializer):
    filters = ReportingFilters()
    summary = ReportingSummary()
    cohort = ReportingCohort()
    cash = ReportingCash()
    delivery = ReportingDelivery()
    comparison = ReportingComparison()
    trend = ReportingTrend(many=True)
    products = ReportingProduct(many=True)
    meta = ReportingMeta()
    return_reasons = ReturnReason(many=True)
    coverage = ReportingCoverage()


class DrilldownRow(serializers.Serializer):
    id = serializers.CharField()
    order_number = serializers.CharField()
    product_id = serializers.UUIDField(allow_null=True)
    product_name = serializers.CharField()
    sku = serializers.CharField()
    quantity = serializers.IntegerField(allow_null=True)
    value = serializers.CharField(allow_null=True)
    event_at = serializers.DateTimeField()
    status = serializers.CharField()
    source = serializers.CharField()


class DrilldownResponse(serializers.Serializer):
    metric = serializers.CharField()
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    results = DrilldownRow(many=True)


class VariantRow(serializers.Serializer):
    sku_id = serializers.UUIDField()
    code = serializers.CharField()
    label = serializers.CharField()
    is_active = serializers.BooleanField()
    ordered_units = serializers.IntegerField()
    cancelled_units = serializers.IntegerField()
    delivered_units = serializers.IntegerField()
    returned_units = serializers.IntegerField()
    delivered_value = serializers.CharField()
    returned_value = serializers.CharField()
    refunded_amount = serializers.CharField()
    net_delivered_value = serializers.CharField()


class VariantProduct(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class VariantFilters(serializers.Serializer):
    product_id = serializers.UUIDField()
    start = serializers.DateField()
    end = serializers.DateField()
    timezone = serializers.CharField()
    currency = serializers.CharField()


class VariantResponse(serializers.Serializer):
    product = VariantProduct()
    filters = VariantFilters()
    results = VariantRow(many=True)


FILTER_PARAMETERS = [OpenApiParameter("start", OpenApiTypes.DATE), OpenApiParameter("end", OpenApiTypes.DATE),
                     OpenApiParameter("product_ids", OpenApiTypes.STR, description="Comma-separated UUIDs; at most 20.")]
METRIC_PARAMETER = OpenApiParameter("metric", OpenApiTypes.STR, enum=["orders", "ordered_units", "cancelled_units", "delivered_units", "returned_units", "refunds"])


@extend_schema(operation_id="analytics_overview", parameters=FILTER_PARAMETERS, responses=AnalyticsResponse, tags=["Analytics"])
@api_view(["GET"])
@permission_classes([IsStaffReader])
def overview(request):
    filters = filters_from_params(request.query_params)
    filters["product_ids"] = sorted(set(filters["product_ids"]))
    payload, cache_status = cached_overview(filters, analytics)
    response = Response(payload)
    response["X-Analytics-Cache"] = cache_status
    # Browser/proxy caches must not bypass the committed revision check.
    response["Cache-Control"] = "private, no-store"
    return response


@extend_schema(operation_id="analytics_variants", parameters=[OpenApiParameter("product_id", OpenApiTypes.UUID, required=True),
                                                             OpenApiParameter("start", OpenApiTypes.DATE), OpenApiParameter("end", OpenApiTypes.DATE)],
               responses=VariantResponse, tags=["Analytics"])
@api_view(["GET"])
@permission_classes([IsStaffReader])
def variants(request):
    try:
        product_id = str(UUID(request.query_params.get("product_id", "")))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValidationError({"product_id": "One product UUID is required."}) from exc
    filters = filters_from_params({"start": request.query_params.get("start"), "end": request.query_params.get("end"), "product_ids": product_id})
    response = Response(variant_analytics(product_id, filters))
    response["Cache-Control"] = "private, no-store"
    return response


@extend_schema(operation_id="analytics_drilldown", parameters=FILTER_PARAMETERS + [METRIC_PARAMETER, OpenApiParameter("page", OpenApiTypes.INT), OpenApiParameter("page_size", OpenApiTypes.INT)],
               responses=DrilldownResponse, tags=["Analytics"])
@api_view(["GET"])
@permission_classes([IsStaffReader])
def detail(request):
    metric = request.query_params.get("metric", "delivered_units")
    rows = drilldown(filters_from_params(request.query_params), metric)
    try:
        page = max(1, int(request.query_params.get("page", 1)))
        size = min(200, max(1, int(request.query_params.get("page_size", 50))))
    except ValueError as exc:
        raise ValidationError("page and page_size must be integers.") from exc
    return Response({"metric": metric, "count": len(rows), "page": page, "page_size": size,
                     "results": rows[(page - 1) * size:page * size]})


def _safe_cell(value):
    value = "" if value is None else str(value)
    # Prevent spreadsheet formula execution when exports are opened in Excel.
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


@extend_schema(operation_id="analytics_export", parameters=FILTER_PARAMETERS + [METRIC_PARAMETER],
               responses={(200, "text/csv"): OpenApiResponse(OpenApiTypes.STR, description="Redacted rows using the same filter as drill-down.")}, tags=["Analytics"])
@api_view(["GET"])
@permission_classes([IsStaffReader])
def export(request):
    metric = request.query_params.get("metric", "delivered_units")
    rows = drilldown(filters_from_params(request.query_params), metric)
    buffer = io.StringIO()
    fields = ["id", "order_number", "product_id", "product_name", "sku", "quantity", "value", "event_at", "status", "source"]
    writer = csv.DictWriter(buffer, fields)
    writer.writeheader()
    writer.writerows({key: _safe_cell(value) for key, value in row.items()} for row in rows)
    response = HttpResponse(buffer.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="productstat-{metric}.csv"'
    return response


urlpatterns = [path("", overview), path("variants/", variants), path("drilldown/", detail), path("export/", export)]
