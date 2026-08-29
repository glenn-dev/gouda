from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('ledger', '0008_observation_resolution_boundary'),
    ]

    operations = [
        migrations.CreateModel(
            name='BciHistoricalPdfBatchEvidence',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('statement_id', models.CharField(max_length=64)),
                ('source_account_id', models.CharField(max_length=64)),
                ('statement_currency', models.CharField(max_length=3)),
                ('gir_version', models.CharField(max_length=64)),
                ('extraction_profile_version', models.CharField(max_length=64)),
                ('provenance_schema_version', models.CharField(choices=[('bci-historical-field-provenance-v1', 'bci-historical-field-provenance-v1')], max_length=64)),
                ('metadata_provenance', models.JSONField()),
                ('reconciliation_provenance', models.JSONField()),
                ('reconciliation_checks', models.JSONField()),
                ('reconciliation_missing_operands', models.JSONField(blank=True, default=list)),
                ('printed_total_debits', models.DecimalField(blank=True, decimal_places=2, max_digits=20, null=True)),
                ('printed_total_credits', models.DecimalField(blank=True, decimal_places=2, max_digits=20, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='BciHistoricalPdfRecordEvidence',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('page_ordinal', models.PositiveIntegerField()),
                ('source_row_ordinal', models.PositiveIntegerField(blank=True, null=True)),
                ('line_ordinals', models.JSONField()),
                ('token_ordinals', models.JSONField()),
                ('field_provenance', models.JSONField()),
                ('source_date_text', models.TextField(blank=True, null=True)),
                ('accounting_date', models.DateField(blank=True, null=True)),
                ('transaction_date', models.DateField(blank=True, null=True)),
                ('branch', models.TextField(blank=True, null=True)),
                ('description', models.TextField(blank=True, null=True)),
                ('source_reference', models.TextField(blank=True, null=True)),
                ('debit', models.DecimalField(blank=True, decimal_places=2, max_digits=20, null=True)),
                ('credit', models.DecimalField(blank=True, decimal_places=2, max_digits=20, null=True)),
                ('signed_amount', models.DecimalField(blank=True, decimal_places=2, max_digits=20, null=True)),
                ('running_balance', models.DecimalField(blank=True, decimal_places=2, max_digits=20, null=True)),
                ('currency', models.CharField(blank=True, max_length=3, null=True)),
            ],
        ),
        migrations.RemoveConstraint(model_name='importbatch', name='batch_source_kind_known'),
        migrations.RemoveConstraint(model_name='importbatch', name='batch_tdc_sheet_fields_null'),
        migrations.RemoveConstraint(model_name='rawrecord', name='raw_record_kind_known'),
        migrations.RemoveConstraint(model_name='rawrecord', name='raw_record_kind_shape'),
        migrations.RemoveConstraint(model_name='rawrecord', name='raw_record_xlsx_amount_shape'),
        migrations.AlterField(
            model_name='importbatch',
            name='source_kind',
            field=models.CharField(choices=[('SANTANDER_CURRENT_ACCOUNT_XLSX', 'Santander current-account XLSX'), ('SANTANDER_CREDIT_CARD_PDF', 'Santander credit-card PDF'), ('BCI_HISTORICAL_CURRENT_ACCOUNT_PDF', 'BCI historical current-account PDF')], max_length=64),
        ),
        migrations.AlterField(
            model_name='importbatch',
            name='source_variant',
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AlterField(
            model_name='rawrecord',
            name='record_kind',
            field=models.CharField(choices=[('SANTANDER_XLSX_ROW', 'Santander XLSX row'), ('SANTANDER_TDC_PDF_RECORD', 'Santander TDC PDF record'), ('BCI_HISTORICAL_PDF_RECORD', 'BCI historical PDF record')], max_length=32),
        ),
        migrations.AddConstraint(
            model_name='importbatch',
            constraint=models.CheckConstraint(check=models.Q(('source_kind__in', ['SANTANDER_CURRENT_ACCOUNT_XLSX', 'SANTANDER_CREDIT_CARD_PDF', 'BCI_HISTORICAL_CURRENT_ACCOUNT_PDF'])), name='batch_source_kind_known'),
        ),
        migrations.AddConstraint(
            model_name='importbatch',
            constraint=models.CheckConstraint(check=models.Q(('source_kind', 'SANTANDER_CURRENT_ACCOUNT_XLSX'), models.Q(('sheet_alias__isnull', True), ('source_kind', 'SANTANDER_CREDIT_CARD_PDF'), ('worksheet_name__isnull', True), ('worksheet_ordinal__isnull', True)), models.Q(('sheet_alias__isnull', True), ('source_kind', 'BCI_HISTORICAL_CURRENT_ACCOUNT_PDF'), ('worksheet_name__isnull', True), ('worksheet_ordinal__isnull', True)), _connector='OR'), name='batch_tdc_sheet_fields_null'),
        ),
        migrations.AddConstraint(
            model_name='rawrecord',
            constraint=models.CheckConstraint(check=models.Q(('record_kind__in', ['SANTANDER_XLSX_ROW', 'SANTANDER_TDC_PDF_RECORD', 'BCI_HISTORICAL_PDF_RECORD'])), name='raw_record_kind_known'),
        ),
        migrations.AddConstraint(
            model_name='rawrecord',
            constraint=models.CheckConstraint(check=models.Q(models.Q(('raw_cells__isnull', False), ('record_kind', 'SANTANDER_XLSX_ROW'), ('row_class__isnull', False), ('row_number__isnull', False)), models.Q(('raw_cells__isnull', True), ('record_kind', 'SANTANDER_TDC_PDF_RECORD'), ('row_class__isnull', True), ('row_number__isnull', True), ('xlsx_amount_source_column__isnull', True)), models.Q(('raw_cells__isnull', True), ('record_kind', 'BCI_HISTORICAL_PDF_RECORD'), ('row_class__isnull', True), ('row_number__isnull', True), ('xlsx_amount_source_column__isnull', True)), _connector='OR'), name='raw_record_kind_shape'),
        ),
        migrations.AddConstraint(
            model_name='rawrecord',
            constraint=models.CheckConstraint(check=models.Q(models.Q(('parse_outcome', 'PARSED'), ('record_kind', 'SANTANDER_XLSX_ROW'), ('xlsx_amount_source_column__in', ['E', 'F'])), models.Q(('parse_outcome__in', ['IGNORED', 'REJECTED']), ('record_kind', 'SANTANDER_XLSX_ROW'), ('xlsx_amount_source_column__isnull', True)), models.Q(('record_kind', 'SANTANDER_TDC_PDF_RECORD'), ('xlsx_amount_source_column__isnull', True)), models.Q(('record_kind', 'BCI_HISTORICAL_PDF_RECORD'), ('xlsx_amount_source_column__isnull', True)), _connector='OR'), name='raw_record_xlsx_amount_shape'),
        ),
        migrations.AddField(
            model_name='bcihistoricalpdfrecordevidence',
            name='raw_record',
            field=models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='bci_historical_pdf_evidence', to='ledger.rawrecord'),
        ),
        migrations.AddField(
            model_name='bcihistoricalpdfbatchevidence',
            name='import_batch',
            field=models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='bci_historical_pdf_evidence', to='ledger.importbatch'),
        ),
        migrations.AddConstraint(model_name='bcihistoricalpdfrecordevidence', constraint=models.CheckConstraint(check=models.Q(('page_ordinal__gt', 0)), name='bci_record_page_positive')),
        migrations.AddConstraint(model_name='bcihistoricalpdfrecordevidence', constraint=models.CheckConstraint(check=models.Q(('source_row_ordinal__isnull', True), ('source_row_ordinal__gt', 0), _connector='OR'), name='bci_record_row_positive')),
        migrations.AddConstraint(model_name='bcihistoricalpdfrecordevidence', constraint=models.CheckConstraint(check=models.Q(('currency__isnull', True), ('currency', 'CLP'), _connector='OR'), name='bci_record_currency_clp')),
        migrations.AddConstraint(model_name='bcihistoricalpdfbatchevidence', constraint=models.CheckConstraint(check=models.Q(('statement_id__regex', '^[0-9]+$')), name='bci_batch_statement_id_shape')),
        migrations.AddConstraint(model_name='bcihistoricalpdfbatchevidence', constraint=models.CheckConstraint(check=models.Q(('source_account_id__regex', '^[0-9]+$')), name='bci_batch_source_account_shape')),
        migrations.AddConstraint(model_name='bcihistoricalpdfbatchevidence', constraint=models.CheckConstraint(check=models.Q(('statement_currency', 'CLP')), name='bci_batch_currency_clp')),
        migrations.AddConstraint(model_name='bcihistoricalpdfbatchevidence', constraint=models.CheckConstraint(check=models.Q(models.Q(('gir_version', ''), _negated=True), models.Q(('extraction_profile_version', ''), _negated=True)), name='bci_batch_versions_nonempty')),
    ]
