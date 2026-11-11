from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orchestrator', '0006_remove_discordbotconfig_get_role_message_id_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='discordaccount',
            name='is_member',
            field=models.BooleanField(default=True, help_text='Whether the account currently belongs to the server'),
        ),
    ]
