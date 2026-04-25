import re
from django.db import migrations, models


def populate_normalized_name(apps, schema_editor):
    Game = apps.get_model('library', 'Game')
    for game in Game.objects.all():
        game.normalized_name = re.sub(r'[^a-z0-9]', '', game.name.lower())
        game.save(update_fields=['normalized_name'])


class Migration(migrations.Migration):

    dependencies = [
        ('library', '0002_usergame_source_alter_game_steam_app_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='game',
            name='normalized_name',
            field=models.CharField(blank=True, default='', max_length=256),
        ),
        migrations.AddIndex(
            model_name='game',
            index=models.Index(fields=['normalized_name'], name='library_gam_norm_idx'),
        ),
        migrations.RunPython(populate_normalized_name, migrations.RunPython.noop),
    ]
