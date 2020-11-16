# Generated by Django 3.1.1 on 2020-11-13 10:53

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("algorithms", "0029_remove_job_image"),
    ]

    operations = [
        migrations.AddField(
            model_name="job",
            name="viewer_groups",
            field=models.ManyToManyField(
                help_text="Which groups should have permission to view this job?",
                to="auth.Group",
            ),
        ),
        migrations.AddField(
            model_name="job",
            name="viewers",
            field=models.OneToOneField(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="viewers_of_algorithm_job",
                to="auth.group",
            ),
        ),
    ]
