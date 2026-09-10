"""Narrow versioned HTTP delivery routes."""

from django.urls import path

from gouda.ledger.api import (
    AccountDiscoveryView,
    CanonicalMovementReportView,
    CategoryDiscoveryView,
)
from gouda.ledger.classification_api import (
    ClassificationWriteCapabilityView, MovementClassificationView,
)
from gouda.ledger.financial_import_api import (
    FinancialImportCapabilityView, SantanderCurrentAccountImportView,
)


urlpatterns = [
    path(
        "api/v1/local/financial-import-capability/",
        FinancialImportCapabilityView.as_view(),
        name="financial-import-capability",
    ),
    path(
        "api/v1/accounts/<str:account_uuid>/imports/santander-current-account-xlsx/",
        SantanderCurrentAccountImportView.as_view(),
        name="santander-current-account-import",
    ),
    path(
        "api/v1/local/classification-write-capability/",
        ClassificationWriteCapabilityView.as_view(),
        name="classification-write-capability",
    ),
    path(
        "api/v1/accounts/<str:account_uuid>/movements/<str:movement_uuid>/classification/",
        MovementClassificationView.as_view(),
        name="movement-classification",
    ),
    path(
        "api/v1/categories/",
        CategoryDiscoveryView.as_view(),
        name="category-discovery",
    ),
    path(
        "api/v1/accounts/",
        AccountDiscoveryView.as_view(),
        name="account-discovery",
    ),
    path(
        "api/v1/accounts/<str:account_uuid>/movements/",
        CanonicalMovementReportView.as_view(),
        name="canonical-movement-report",
    ),
]
