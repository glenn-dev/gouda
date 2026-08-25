import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q


XLSX_SOURCE_KIND = "SANTANDER_CURRENT_ACCOUNT_XLSX"
TDC_SOURCE_KIND = "SANTANDER_CREDIT_CARD_PDF"
XLSX_RECORD_KIND = "SANTANDER_XLSX_ROW"
TDC_RECORD_KIND = "SANTANDER_TDC_PDF_RECORD"
PROVENANCE_SCHEMA_VERSION = "santander-tdc-field-provenance-v1"


def guard_reverse_checkpoint_a(apps, schema_editor):
    SourceArtifact = apps.get_model("ledger", "SourceArtifact")
    ImportBatch = apps.get_model("ledger", "ImportBatch")
    RawRecord = apps.get_model("ledger", "RawRecord")
    BatchEvidence = apps.get_model("ledger", "SantanderTdcPdfBatchEvidence")
    RecordEvidence = apps.get_model("ledger", "SantanderTdcPdfRecordEvidence")

    if BatchEvidence.objects.exists() or RecordEvidence.objects.exists():
        raise RuntimeError("Cannot reverse Checkpoint A while Santander TDC evidence exists.")
    if ImportBatch.objects.exclude(source_kind=XLSX_SOURCE_KIND).exists():
        raise RuntimeError("Cannot reverse Checkpoint A while non-XLSX batches exist.")
    if RawRecord.objects.exclude(record_kind=XLSX_RECORD_KIND).exists():
        raise RuntimeError("Cannot reverse Checkpoint A while non-XLSX records exist.")
    for artifact in SourceArtifact.objects.all():
        source_kinds = set(
            ImportBatch.objects.filter(source_artifact_id=artifact.pk)
            .values_list("source_kind", flat=True)
            .distinct()
        )
        if source_kinds != {XLSX_SOURCE_KIND}:
            raise RuntimeError(
                "Cannot reverse Checkpoint A when artifact interpretation is absent or ambiguous."
            )


class Migration(migrations.Migration):
    dependencies = [("ledger", "0005_checkpoint_a_backfill")]

    operations = [
        migrations.CreateModel(
            name="SantanderTdcPdfBatchEvidence",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "provenance_schema_version",
                    models.CharField(
                        choices=[
                            (PROVENANCE_SCHEMA_VERSION, PROVENANCE_SCHEMA_VERSION)
                        ],
                        max_length=64,
                    ),
                ),
                ("gir_version", models.CharField(max_length=64)),
                ("extraction_profile_version", models.CharField(max_length=64)),
                ("billing_cutoff_date", models.DateField()),
                ("payment_due_date", models.DateField()),
                (
                    "statement_currency",
                    models.CharField(blank=True, max_length=3, null=True),
                ),
                ("card_product_context", models.CharField(max_length=64)),
                ("card_last_four", models.CharField(max_length=4)),
                ("metadata_provenance", models.JSONField()),
                (
                    "reconciliation_missing_operands",
                    models.JSONField(blank=True, default=list),
                ),
                ("reconciliation_provenance", models.JSONField()),
                (
                    "purchases_charges",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=20, null=True
                    ),
                ),
                (
                    "payments_credits",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=20, null=True
                    ),
                ),
                (
                    "financial_charges",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=20, null=True
                    ),
                ),
                (
                    "import_batch",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="santander_tdc_pdf_evidence",
                        to="ledger.importbatch",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="SantanderTdcPdfRecordEvidence",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("page_ordinal", models.PositiveIntegerField()),
                (
                    "section",
                    models.CharField(
                        choices=[
                            ("preamble", "Preamble"),
                            ("statement_summary", "Statement summary"),
                            ("billed_domestic", "Billed domestic"),
                            ("billed_international", "Billed international"),
                            ("billed_installment", "Billed installment"),
                            ("billed_other", "Billed other"),
                            ("payments_credits", "Payments and credits"),
                            ("financial_charges", "Financial charges"),
                            ("unbilled", "Unbilled"),
                            ("footer_legal", "Footer/legal"),
                            ("end", "End"),
                        ],
                        max_length=32,
                    ),
                ),
                ("row_group_ordinal", models.PositiveIntegerField()),
                ("line_ordinals", models.JSONField()),
                ("token_ordinals", models.JSONField()),
                ("field_provenance", models.JSONField()),
                ("transaction_date", models.DateField(blank=True, null=True)),
                ("description_detail", models.TextField(blank=True, null=True)),
                ("location", models.TextField(blank=True, null=True)),
                ("reference_authorization", models.TextField(blank=True, null=True)),
                (
                    "billed_currency",
                    models.CharField(blank=True, max_length=3, null=True),
                ),
                (
                    "billed_amount",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=20, null=True
                    ),
                ),
                (
                    "original_currency",
                    models.CharField(blank=True, max_length=3, null=True),
                ),
                (
                    "original_amount",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=20, null=True
                    ),
                ),
                (
                    "section_category",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("purchase_charge", "Purchase/charge"),
                            ("payment", "Payment"),
                            ("credit_refund", "Credit/refund"),
                            ("interest", "Interest"),
                            ("commission", "Commission"),
                            ("tax", "Tax"),
                            ("insurance", "Insurance"),
                            ("cash_advance", "Cash advance"),
                        ],
                        max_length=32,
                        null=True,
                    ),
                ),
                (
                    "debt_effect",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=20, null=True
                    ),
                ),
                (
                    "installment_number",
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                (
                    "installment_amount",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=20, null=True
                    ),
                ),
                ("header_profile", models.CharField(blank=True, max_length=64, null=True)),
                (
                    "raw_record",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="santander_tdc_pdf_evidence",
                        to="ledger.rawrecord",
                    ),
                ),
            ],
        ),
        migrations.RemoveConstraint(
            model_name="movement",
            name="movement_amount_column_known",
        ),
        migrations.RemoveConstraint(
            model_name="rawrecord",
            name="raw_record_positive_row",
        ),
        migrations.AlterField(
            model_name="importbatch",
            name="source_kind",
            field=models.CharField(
                choices=[
                    (
                        XLSX_SOURCE_KIND,
                        "Santander current-account XLSX",
                    ),
                    (TDC_SOURCE_KIND, "Santander credit-card PDF"),
                ],
                max_length=64,
            ),
        ),
        migrations.AlterField(
            model_name="rawrecord",
            name="record_kind",
            field=models.CharField(
                choices=[
                    (XLSX_RECORD_KIND, "Santander XLSX row"),
                    (TDC_RECORD_KIND, "Santander TDC PDF record"),
                ],
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="rawrecord",
            name="record_ordinal",
            field=models.PositiveIntegerField(),
        ),
        migrations.AlterField(
            model_name="rawrecord",
            name="row_number",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="rawrecord",
            name="raw_cells",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="rawrecord",
            name="row_class",
            field=models.CharField(
                blank=True,
                choices=[
                    ("metadata", "Metadata"),
                    ("movement_candidate", "Movement candidate"),
                    ("header", "Header"),
                    ("blank", "Blank"),
                    ("auxiliary", "Auxiliary"),
                ],
                max_length=32,
                null=True,
            ),
        ),
        migrations.RemoveField(
            model_name="movement",
            name="amount_source_column",
        ),
        migrations.RemoveField(
            model_name="sourceartifact",
            name="source_kind",
        ),
        migrations.AddConstraint(
            model_name="importbatch",
            constraint=models.CheckConstraint(
                check=Q(source_kind__in=[XLSX_SOURCE_KIND, TDC_SOURCE_KIND]),
                name="batch_source_kind_known",
            ),
        ),
        migrations.AddConstraint(
            model_name="importbatch",
            constraint=models.CheckConstraint(
                check=(
                    Q(source_kind=XLSX_SOURCE_KIND)
                    | Q(
                        source_kind=TDC_SOURCE_KIND,
                        sheet_alias__isnull=True,
                        worksheet_name__isnull=True,
                        worksheet_ordinal__isnull=True,
                    )
                ),
                name="batch_tdc_sheet_fields_null",
            ),
        ),
        migrations.AddConstraint(
            model_name="rawrecord",
            constraint=models.UniqueConstraint(
                fields=("import_batch", "record_ordinal"),
                name="one_raw_record_per_batch_ordinal",
            ),
        ),
        migrations.AddConstraint(
            model_name="rawrecord",
            constraint=models.CheckConstraint(
                check=Q(record_ordinal__gt=0),
                name="raw_record_positive_ordinal",
            ),
        ),
        migrations.AddConstraint(
            model_name="rawrecord",
            constraint=models.CheckConstraint(
                check=Q(row_number__isnull=True) | Q(row_number__gt=0),
                name="raw_record_positive_row",
            ),
        ),
        migrations.AddConstraint(
            model_name="rawrecord",
            constraint=models.CheckConstraint(
                check=Q(record_kind__in=[XLSX_RECORD_KIND, TDC_RECORD_KIND]),
                name="raw_record_kind_known",
            ),
        ),
        migrations.AddConstraint(
            model_name="rawrecord",
            constraint=models.CheckConstraint(
                check=(
                    Q(
                        record_kind=XLSX_RECORD_KIND,
                        row_number__isnull=False,
                        raw_cells__isnull=False,
                        row_class__isnull=False,
                    )
                    | Q(
                        record_kind=TDC_RECORD_KIND,
                        row_number__isnull=True,
                        raw_cells__isnull=True,
                        row_class__isnull=True,
                        xlsx_amount_source_column__isnull=True,
                    )
                ),
                name="raw_record_kind_shape",
            ),
        ),
        migrations.AddConstraint(
            model_name="rawrecord",
            constraint=models.CheckConstraint(
                check=(
                    Q(
                        record_kind=XLSX_RECORD_KIND,
                        parse_outcome="PARSED",
                        xlsx_amount_source_column__in=["E", "F"],
                    )
                    | Q(
                        record_kind=XLSX_RECORD_KIND,
                        parse_outcome__in=["IGNORED", "REJECTED"],
                        xlsx_amount_source_column__isnull=True,
                    )
                    | Q(
                        record_kind=TDC_RECORD_KIND,
                        xlsx_amount_source_column__isnull=True,
                    )
                ),
                name="raw_record_xlsx_amount_shape",
            ),
        ),
        migrations.AddConstraint(
            model_name="santandertdcpdfrecordevidence",
            constraint=models.CheckConstraint(
                check=Q(page_ordinal__gt=0), name="tdc_record_page_positive"
            ),
        ),
        migrations.AddConstraint(
            model_name="santandertdcpdfrecordevidence",
            constraint=models.CheckConstraint(
                check=Q(
                    section__in=[
                        "preamble",
                        "statement_summary",
                        "billed_domestic",
                        "billed_international",
                        "billed_installment",
                        "billed_other",
                        "payments_credits",
                        "financial_charges",
                        "unbilled",
                        "footer_legal",
                        "end",
                    ]
                ),
                name="tdc_record_section_known",
            ),
        ),
        migrations.AddConstraint(
            model_name="santandertdcpdfrecordevidence",
            constraint=models.CheckConstraint(
                check=Q(section_category__isnull=True)
                | Q(
                    section_category__in=[
                        "purchase_charge",
                        "payment",
                        "credit_refund",
                        "interest",
                        "commission",
                        "tax",
                        "insurance",
                        "cash_advance",
                    ]
                ),
                name="tdc_record_category_known",
            ),
        ),
        migrations.AddConstraint(
            model_name="santandertdcpdfrecordevidence",
            constraint=models.CheckConstraint(
                check=Q(billed_currency__isnull=True)
                | Q(billed_currency__regex=r"^[A-Z]{3}$"),
                name="tdc_record_billed_currency_iso",
            ),
        ),
        migrations.AddConstraint(
            model_name="santandertdcpdfrecordevidence",
            constraint=models.CheckConstraint(
                check=Q(original_currency__isnull=True)
                | Q(original_currency__regex=r"^[A-Z]{3}$"),
                name="tdc_record_original_currency_iso",
            ),
        ),
        migrations.AddConstraint(
            model_name="santandertdcpdfrecordevidence",
            constraint=models.CheckConstraint(
                check=(
                    Q(original_amount__isnull=True, original_currency__isnull=True)
                    | Q(original_amount__isnull=False, original_currency__isnull=False)
                ),
                name="tdc_record_original_pair",
            ),
        ),
        migrations.AddConstraint(
            model_name="santandertdcpdfbatchevidence",
            constraint=models.CheckConstraint(
                check=Q(provenance_schema_version=PROVENANCE_SCHEMA_VERSION),
                name="tdc_batch_provenance_schema_known",
            ),
        ),
        migrations.AddConstraint(
            model_name="santandertdcpdfbatchevidence",
            constraint=models.CheckConstraint(
                check=(
                    ~Q(gir_version="")
                    & ~Q(extraction_profile_version="")
                    & ~Q(card_product_context="")
                ),
                name="tdc_batch_required_text_nonempty",
            ),
        ),
        migrations.AddConstraint(
            model_name="santandertdcpdfbatchevidence",
            constraint=models.CheckConstraint(
                check=Q(card_last_four__regex=r"^[0-9]{4}$"),
                name="tdc_batch_card_last_four_shape",
            ),
        ),
        migrations.AddConstraint(
            model_name="santandertdcpdfbatchevidence",
            constraint=models.CheckConstraint(
                check=Q(statement_currency__isnull=True)
                | Q(statement_currency__regex=r"^[A-Z]{3}$"),
                name="tdc_batch_currency_iso_like",
            ),
        ),
        migrations.RunPython(migrations.RunPython.noop, guard_reverse_checkpoint_a),
    ]
