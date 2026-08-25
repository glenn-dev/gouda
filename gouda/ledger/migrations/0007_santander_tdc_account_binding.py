import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q


def guard_reverse_binding(apps, schema_editor):
    Binding = apps.get_model("ledger", "SantanderTdcAccountBinding")
    if Binding.objects.exists():
        raise RuntimeError(
            "Cannot reverse Santander TDC account binding migration while bindings exist."
        )


class Migration(migrations.Migration):
    dependencies = [("ledger", "0006_checkpoint_a_persistence_boundary")]

    operations = [
        migrations.CreateModel(
            name="SantanderTdcAccountBinding",
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
                ("card_last_four", models.CharField(max_length=4)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "account",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="santander_tdc_binding",
                        to="ledger.account",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="santandertdcaccountbinding",
            constraint=models.CheckConstraint(
                check=Q(card_last_four__regex=r"^[0-9]{4}$"),
                name="tdc_binding_card_last_four_shape",
            ),
        ),
        migrations.RunPython(migrations.RunPython.noop, guard_reverse_binding),
    ]
