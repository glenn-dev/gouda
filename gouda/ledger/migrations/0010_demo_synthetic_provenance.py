from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("ledger", "0009_bci_historical_pdf")]

    operations = [
        migrations.RemoveConstraint(
            model_name="importbatch",
            name="batch_source_kind_known",
        ),
        migrations.RemoveConstraint(
            model_name="importbatch",
            name="batch_tdc_sheet_fields_null",
        ),
        migrations.RemoveConstraint(
            model_name="rawrecord",
            name="raw_record_kind_known",
        ),
        migrations.RemoveConstraint(
            model_name="rawrecord",
            name="raw_record_kind_shape",
        ),
        migrations.RemoveConstraint(
            model_name="rawrecord",
            name="raw_record_xlsx_amount_shape",
        ),
        migrations.AlterField(
            model_name="importbatch",
            name="source_kind",
            field=models.CharField(
                choices=[
                    (
                        "SANTANDER_CURRENT_ACCOUNT_XLSX",
                        "Santander current-account XLSX",
                    ),
                    (
                        "SANTANDER_CREDIT_CARD_PDF",
                        "Santander credit-card PDF",
                    ),
                    (
                        "BCI_HISTORICAL_CURRENT_ACCOUNT_PDF",
                        "BCI historical current-account PDF",
                    ),
                    ("DEMO_SYNTHETIC", "Synthetic local demo"),
                ],
                max_length=64,
            ),
        ),
        migrations.AlterField(
            model_name="rawrecord",
            name="record_kind",
            field=models.CharField(
                choices=[
                    ("SANTANDER_XLSX_ROW", "Santander XLSX row"),
                    ("SANTANDER_TDC_PDF_RECORD", "Santander TDC PDF record"),
                    ("BCI_HISTORICAL_PDF_RECORD", "BCI historical PDF record"),
                    ("DEMO_SYNTHETIC_RECORD", "Synthetic demo record"),
                ],
                max_length=32,
            ),
        ),
        migrations.AddConstraint(
            model_name="importbatch",
            constraint=models.CheckConstraint(
                check=models.Q(
                    source_kind__in=[
                        "SANTANDER_CURRENT_ACCOUNT_XLSX",
                        "SANTANDER_CREDIT_CARD_PDF",
                        "BCI_HISTORICAL_CURRENT_ACCOUNT_PDF",
                        "DEMO_SYNTHETIC",
                    ]
                ),
                name="batch_source_kind_known",
            ),
        ),
        migrations.AddConstraint(
            model_name="importbatch",
            constraint=models.CheckConstraint(
                check=(
                    models.Q(source_kind="SANTANDER_CURRENT_ACCOUNT_XLSX")
                    | models.Q(
                        source_kind="SANTANDER_CREDIT_CARD_PDF",
                        sheet_alias__isnull=True,
                        worksheet_name__isnull=True,
                        worksheet_ordinal__isnull=True,
                    )
                    | models.Q(
                        source_kind="BCI_HISTORICAL_CURRENT_ACCOUNT_PDF",
                        sheet_alias__isnull=True,
                        worksheet_name__isnull=True,
                        worksheet_ordinal__isnull=True,
                    )
                    | models.Q(
                        source_kind="DEMO_SYNTHETIC",
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
            constraint=models.CheckConstraint(
                check=models.Q(
                    record_kind__in=[
                        "SANTANDER_XLSX_ROW",
                        "SANTANDER_TDC_PDF_RECORD",
                        "BCI_HISTORICAL_PDF_RECORD",
                        "DEMO_SYNTHETIC_RECORD",
                    ]
                ),
                name="raw_record_kind_known",
            ),
        ),
        migrations.AddConstraint(
            model_name="rawrecord",
            constraint=models.CheckConstraint(
                check=(
                    models.Q(
                        record_kind="SANTANDER_XLSX_ROW",
                        row_number__isnull=False,
                        raw_cells__isnull=False,
                        row_class__isnull=False,
                    )
                    | models.Q(
                        record_kind="SANTANDER_TDC_PDF_RECORD",
                        row_number__isnull=True,
                        raw_cells__isnull=True,
                        row_class__isnull=True,
                        xlsx_amount_source_column__isnull=True,
                    )
                    | models.Q(
                        record_kind="BCI_HISTORICAL_PDF_RECORD",
                        row_number__isnull=True,
                        raw_cells__isnull=True,
                        row_class__isnull=True,
                        xlsx_amount_source_column__isnull=True,
                    )
                    | models.Q(
                        record_kind="DEMO_SYNTHETIC_RECORD",
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
                    models.Q(
                        record_kind="SANTANDER_XLSX_ROW",
                        parse_outcome="PARSED",
                        xlsx_amount_source_column__in=["E", "F"],
                    )
                    | models.Q(
                        record_kind="SANTANDER_XLSX_ROW",
                        parse_outcome__in=["IGNORED", "REJECTED"],
                        xlsx_amount_source_column__isnull=True,
                    )
                    | models.Q(
                        record_kind="SANTANDER_TDC_PDF_RECORD",
                        xlsx_amount_source_column__isnull=True,
                    )
                    | models.Q(
                        record_kind="BCI_HISTORICAL_PDF_RECORD",
                        xlsx_amount_source_column__isnull=True,
                    )
                    | models.Q(
                        record_kind="DEMO_SYNTHETIC_RECORD",
                        xlsx_amount_source_column__isnull=True,
                    )
                ),
                name="raw_record_xlsx_amount_shape",
            ),
        ),
    ]
