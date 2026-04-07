from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0004_job_results_published_job_shortlist_email_sent'),
    ]

    operations = [
        migrations.AddField(
            model_name='job',
            name='open_positions',
            field=models.PositiveIntegerField(default=1, help_text='Number of open positions for this role'),
        ),
    ]