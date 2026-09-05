"""Synthetic canonical graph, also usable with historical migration models."""

from datetime import date
from decimal import Decimal
import hashlib

from django.apps import apps as live_apps
from django.utils import timezone


def make_movement(*, apps=live_apps, label="classification"):
    Account, Artifact, Batch, Raw, Movement = (
        apps.get_model("ledger", name)
        for name in ("Account", "SourceArtifact", "ImportBatch", "RawRecord", "Movement")
    )
    account = Account.objects.create(
        display_name=f"Synthetic {label}", kind="CURRENT",
        economic_orientation="ASSET", currency="CLP",
    )
    content = f"Synthetic {label} artifact".encode()
    artifact = Artifact.objects.create(
        original_filename="synthetic.xlsx", content=content,
        content_digest=hashlib.sha256(content).hexdigest(),
    )
    batch = Batch.objects.create(
        account=account, source_artifact=artifact,
        source_kind="SANTANDER_CURRENT_ACCOUNT_XLSX", source_variant="v1",
        parser_version="synthetic-v1", status="ACCEPTED", parsed_count=1,
        completed_at=timezone.now(), reconciliation_status="NOT_APPLICABLE",
    )
    raw = Raw.objects.create(
        import_batch=batch, record_kind="SANTANDER_XLSX_ROW", record_ordinal=1,
        row_number=1, raw_cells=[{"value": "synthetic"}],
        row_class="movement_candidate", parse_outcome="PARSED",
        xlsx_amount_source_column="E", parser_codes=[],
    )
    return Movement.objects.create(
        account=account, raw_record=raw, occurrence_date=date(2026, 1, 5),
        signed_amount=Decimal("-10.25"), currency="CLP",
        description="Synthetic purchase", source_reference="SYN-CLASSIFICATION",
        running_balance=Decimal("89.75"),
    )
