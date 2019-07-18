# Generated by Django 2.2.3 on 2019-07-18 13:33

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("reader_studies", "0001_initial"),
        ("cases", "0011_auto_20190314_1453"),
    ]

    operations = [
        migrations.AddField(
            model_name="rawimageuploadsession",
            name="reader_study",
            field=models.ForeignKey(
                default=None,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="reader_studies.ReaderStudy",
            ),
        )
    ]
