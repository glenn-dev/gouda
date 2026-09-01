"""Narrow versioned HTTP delivery routes."""

from django.urls import path

from gouda.ledger.api import CanonicalMovementReportView


urlpatterns = [
    path(
        "api/v1/accounts/<str:account_uuid>/movements/",
        CanonicalMovementReportView.as_view(),
        name="canonical-movement-report",
    ),
]
