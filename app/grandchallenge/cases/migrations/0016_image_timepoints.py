# Generated by Django 2.2.6 on 2019-11-04 08:21

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("cases", "0015_auto_20191003_1323")]

    operations = [
        migrations.AddField(
            model_name="image",
            name="timepoints",
            field=models.IntegerField(null=True),
        )
    ]
