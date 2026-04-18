from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("applications", "0003_alter_application_status"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="application",
            name="cover_letter",
        ),
    ]
