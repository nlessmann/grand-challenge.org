# Generated by Django 2.2.6 on 2019-10-02 13:22

import django.contrib.postgres.fields.jsonb
from django.db import migrations

import grandchallenge.core.validators


class Migration(migrations.Migration):

    dependencies = [("reader_studies", "0003_auto_20190921_0017")]

    operations = [
        migrations.AlterField(
            model_name="readerstudy",
            name="hanging_list",
            field=django.contrib.postgres.fields.jsonb.JSONField(
                blank=True,
                default=list,
                validators=[
                    grandchallenge.core.validators.JSONSchemaValidator(
                        schema={
                            "$schema": "http://json-schema.org/draft-06/schema#",
                            "definitions": {},
                            "items": {
                                "$id": "#/items",
                                "additionalProperties": False,
                                "properties": {
                                    "main": {
                                        "$id": "#/items/properties/main",
                                        "default": "",
                                        "examples": ["im1.mhd"],
                                        "pattern": "^(.*)$",
                                        "title": "The Main Schema",
                                        "type": "string",
                                    },
                                    "main-overlay": {
                                        "$id": "#/items/properties/main-overlay",
                                        "default": "",
                                        "examples": ["im1-overlay.mhd"],
                                        "pattern": "^(.*)$",
                                        "title": "The Main Overlay Schema",
                                        "type": "string",
                                    },
                                    "secondary": {
                                        "$id": "#/items/properties/secondary",
                                        "default": "",
                                        "examples": ["im2.mhd"],
                                        "pattern": "^(.*)$",
                                        "title": "The Secondary Schema",
                                        "type": "string",
                                    },
                                    "secondary-overlay": {
                                        "$id": "#/items/properties/secondary-overlay",
                                        "default": "",
                                        "examples": ["im2-overlay.mhd"],
                                        "pattern": "^(.*)$",
                                        "title": "The Secondary Overlay Schema",
                                        "type": "string",
                                    },
                                },
                                "required": ["main"],
                                "title": "The Items Schema",
                                "type": "object",
                            },
                            "title": "The Hanging List Schema",
                            "type": "array",
                        }
                    )
                ],
            ),
        )
    ]