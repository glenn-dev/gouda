from django.db import migrations, models


XLSX_SOURCE_KIND = "SANTANDER_CURRENT_ACCOUNT_XLSX"
XLSX_RECORD_KIND = "SANTANDER_XLSX_ROW"


def backfill_checkpoint_a(apps, schema_editor):
    SourceArtifact = apps.get_model("ledger", "SourceArtifact")
    ImportBatch = apps.get_model("ledger", "ImportBatch")
    RawRecord = apps.get_model("ledger", "RawRecord")
    Movement = apps.get_model("ledger", "Movement")

    unknown_source_kinds = set(
        SourceArtifact.objects.exclude(source_kind=XLSX_SOURCE_KIND)
        .values_list("source_kind", flat=True)
        .distinct()
    )
    if unknown_source_kinds:
        raise RuntimeError("Cannot backfill unknown SourceArtifact source kinds.")

    ImportBatch.objects.update(source_kind=XLSX_SOURCE_KIND)

    invalid_raw = RawRecord.objects.filter(row_number__isnull=True).exists() or RawRecord.objects.filter(
        row_number__lte=0
    ).exists()
    if invalid_raw:
        raise RuntimeError("Cannot backfill RawRecord identity from invalid XLSX row numbers.")
    RawRecord.objects.update(record_kind=XLSX_RECORD_KIND, record_ordinal=models.F("row_number"))

    movements = list(Movement.objects.select_related("raw_record"))
    movement_by_raw_id = {}
    for movement in movements:
        if movement.amount_source_column not in {"E", "F"}:
            raise RuntimeError("Cannot backfill an unknown XLSX amount source column.")
        if movement.raw_record.parse_outcome != "PARSED":
            raise RuntimeError("Cannot backfill an XLSX movement attached to a non-parsed raw record.")
        movement_by_raw_id[movement.raw_record_id] = movement.amount_source_column

    parsed_raw_ids = set(
        RawRecord.objects.filter(parse_outcome="PARSED").values_list("id", flat=True)
    )
    if parsed_raw_ids != set(movement_by_raw_id):
        raise RuntimeError("Cannot backfill parsed XLSX records without exactly one movement.")

    for raw_record_id, amount_source_column in movement_by_raw_id.items():
        RawRecord.objects.filter(pk=raw_record_id).update(
            xlsx_amount_source_column=amount_source_column
        )


def reverse_checkpoint_a(apps, schema_editor):
    SourceArtifact = apps.get_model("ledger", "SourceArtifact")
    ImportBatch = apps.get_model("ledger", "ImportBatch")
    RawRecord = apps.get_model("ledger", "RawRecord")
    Movement = apps.get_model("ledger", "Movement")

    if ImportBatch.objects.exclude(source_kind=XLSX_SOURCE_KIND).exists():
        raise RuntimeError("Cannot reverse source-kind migration with non-XLSX batches.")
    if RawRecord.objects.exclude(record_kind=XLSX_RECORD_KIND).exists():
        raise RuntimeError("Cannot reverse record identity migration with non-XLSX records.")

    for artifact in SourceArtifact.objects.all():
        source_kinds = set(
            ImportBatch.objects.filter(source_artifact_id=artifact.pk)
            .values_list("source_kind", flat=True)
            .distinct()
        )
        if source_kinds != {XLSX_SOURCE_KIND}:
            raise RuntimeError(
                "Cannot reverse source-kind migration when artifact interpretation is absent or ambiguous."
            )
        SourceArtifact.objects.filter(pk=artifact.pk).update(source_kind=XLSX_SOURCE_KIND)

    for raw_record in RawRecord.objects.all():
        if raw_record.record_ordinal is None or raw_record.record_ordinal <= 0:
            raise RuntimeError("Cannot restore an invalid XLSX row number.")
        RawRecord.objects.filter(pk=raw_record.pk).update(row_number=raw_record.record_ordinal)

    for movement in Movement.objects.select_related("raw_record"):
        amount_source_column = movement.raw_record.xlsx_amount_source_column
        if amount_source_column not in {"E", "F"}:
            raise RuntimeError("Cannot restore an XLSX movement amount source column.")
        Movement.objects.filter(pk=movement.pk).update(
            amount_source_column=amount_source_column
        )


class Migration(migrations.Migration):
    dependencies = [("ledger", "0004_account_economic_orientation")]

    operations = [
        migrations.AddField(
            model_name="importbatch",
            name="source_kind",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="rawrecord",
            name="record_kind",
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.AddField(
            model_name="rawrecord",
            name="record_ordinal",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="rawrecord",
            name="xlsx_amount_source_column",
            field=models.CharField(blank=True, max_length=1, null=True),
        ),
        migrations.AlterField(
            model_name="sourceartifact",
            name="source_kind",
            field=models.CharField(
                blank=True,
                choices=[
                    (
                        "SANTANDER_CURRENT_ACCOUNT_XLSX",
                        "Santander current-account XLSX",
                    )
                ],
                max_length=64,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="movement",
            name="amount_source_column",
            field=models.CharField(blank=True, max_length=1, null=True),
        ),
        migrations.RunPython(backfill_checkpoint_a, reverse_checkpoint_a),
    ]
