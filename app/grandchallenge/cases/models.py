# -*- coding: utf-8 -*-
from django.conf import settings
from django.db import models
from django.utils import timezone

from grandchallenge.core.models import UUIDModel
from grandchallenge.core.urlresolvers import reverse
from grandchallenge.core.validators import ExtensionValidator


def case_file_path(instance, filename):
    return f"cases/{instance.case.pk}/{filename}"


class Case(UUIDModel):
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )

    def get_absolute_url(self):
        return reverse("cases:detail", kwargs={"pk": self.pk})


class CaseFile(UUIDModel):
    case = models.ForeignKey(to=Case, on_delete=models.CASCADE)

    file = models.FileField(
        upload_to=case_file_path,
        validators=[
            ExtensionValidator(
                allowed_extensions=('.mhd', '.raw', '.zraw',)
            )
        ],
        help_text=(
            'Select the file for this case.'
        ),
    )


class UPLOAD_SESSION_STATE:
    created = "created"
    queued = "queued"
    running = "running"
    stopped = "stopped"


class RawImageUploadSession(UUIDModel):
    """
    A session keeps track of uploaded files and forms the basis of a processing
    task that tries to make sense of the uploaded files to form normalized
    images that can be fed to processing tasks.
    """
    session_state = models.CharField(
        max_length=16,
        default=UPLOAD_SESSION_STATE.created,
    )

    created_on = models.DateTimeField(
        blank=False,
        default=timezone.now,
    )

    processing_task = models.UUIDField(
        null=True,
        default=None,
    )

    error_message = models.CharField(
        max_length=256,
        blank=False,
        null=True,
        default=None,
    )

    def get_absolute_url(self):
        return reverse(
            "cases:raw-files-session-detail",
            kwargs={
                "pk": self.pk,
            })


class RawImageFile(UUIDModel):
    """
    A raw image file is a file that has been uploaded by a user but was not
    preprocessed to create a standardized image representation.
    """
    upload_session = models.ForeignKey(
        RawImageUploadSession,
        blank=False,
        on_delete=models.CASCADE,
    )

    # Copy in case staged_file_id is set to None
    filename = models.CharField(
        max_length=128,
        blank=False,
    )

    staged_file_id = models.UUIDField(
        blank=True,
        null=True)

    error = models.CharField(
        max_length=256,
        blank=False,
        null=True,
        default=None
    )


def image_file_path(instance, filename):
    return f"images/{instance.image.pk}/{filename}"


class Image(UUIDModel):
    COLOR_SPACE_GRAY = "GRAY"
    COLOR_SPACE_RGB = "RGB"
    COLOR_SPACE_RGBA = "RGB"

    COLOR_SPACES = (
        (COLOR_SPACE_GRAY, "GRAY"),
        (COLOR_SPACE_RGB, "RGB"),
        (COLOR_SPACE_RGBA, "RGBA"),
    )

    COLOR_SPACE_COMPONENTS = {
        COLOR_SPACE_GRAY: 1,
        COLOR_SPACE_RGB: 3,
        COLOR_SPACE_RGBA: 4,
    }

    name = models.CharField(max_length=128)
    origin = models.ForeignKey(
        to=RawImageUploadSession,
        null=True,
        on_delete=models.SET_NULL,
    )
    created_on = models.DateTimeField(
        blank=False,
        default=timezone.now,
    )

    width = models.IntegerField(
        blank=False,
    )
    height = models.IntegerField(
        blank=False,
    )
    depth = models.IntegerField(
        null=True,
    )
    color_space = models.CharField(
        max_length=8,
        blank=False,
        choices=COLOR_SPACES,
    )

    @property
    def shape_without_color(self):
        result = []
        if self.depth is not None:
            result.append(self.depth)
        result.append(self.height)
        result.append(self.width)
        return result

    @property
    def shape(self):
        result = self.shape_without_color
        color_components = self.COLOR_SPACE_COMPONENTS[self.color_space]
        if color_components > 1:
            result.append(color_components)
        return result


class ImageFile(UUIDModel):
    image = models.ForeignKey(
        to=Image,
        null=True,
        on_delete=models.SET_NULL,
    )
    file = models.FileField(
        upload_to=image_file_path,
        blank=False,
    )

