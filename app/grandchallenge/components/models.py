import json
import logging
from decimal import Decimal
from json import JSONDecodeError
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Tuple, Type

from django.conf import settings
from django.core.files import File
from django.db import models
from django.db.models import Avg, F, QuerySet
from django.utils._os import safe_join
from django.utils.text import get_valid_filename
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_extensions.db.fields import AutoSlugField
from docker.errors import NotFound

from grandchallenge.cases.image_builders.metaio_mhd_mha import (
    image_builder_mhd,
)
from grandchallenge.cases.image_builders.tiff import image_builder_tiff
from grandchallenge.cases.models import Image
from grandchallenge.cases.tasks import import_images
from grandchallenge.components.backends.docker import (
    ComponentException,
    Executor,
    get_file,
)
from grandchallenge.components.tasks import execute_job, validate_docker_image
from grandchallenge.components.validators import validate_safe_path
from grandchallenge.core.storage import (
    private_s3_storage,
    protected_s3_storage,
)
from grandchallenge.core.validators import ExtensionValidator

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_INTERFACE_SLUG = "generic-overlay"


class InterfaceKindChoices(models.TextChoices):
    STRING = "STR", _("String")
    INTEGER = "INT", _("Integer")
    FLOAT = "FLT", _("Float")
    BOOL = "BOOL", _("Bool")

    # Annotation Types
    TWO_D_BOUNDING_BOX = "2DBB", _("2D bounding box")
    MULTIPLE_TWO_D_BOUNDING_BOXES = "M2DB", _("Multiple 2D bounding boxes")
    DISTANCE_MEASUREMENT = "DIST", _("Distance measurement")
    MULTIPLE_DISTANCE_MEASUREMENTS = (
        "MDIS",
        _("Multiple distance measurements"),
    )
    POINT = "POIN", _("Point")
    MULTIPLE_POINTS = "MPOI", _("Multiple points")
    POLYGON = "POLY", _("Polygon")
    MULTIPLE_POLYGONS = "MPOL", _("Multiple polygons")

    # Choice Types
    CHOICE = "CHOI", _("Choice")
    MULTIPLE_CHOICE = "MCHO", _("Multiple choice")

    # Image types
    IMAGE = "IMG", _("Image")
    SEGMENTATION = "SEG", _("Segmentation")
    HEAT_MAP = "HMAP", _("Heat Map")

    # Legacy support
    JSON = "JSON", _("JSON file")
    CSV = "CSV", _("CSV file")
    ZIP = "ZIP", _("ZIP file")


class ComponentInterface(models.Model):
    Kind = InterfaceKindChoices

    title = models.CharField(
        max_length=255,
        help_text="Human readable name of this input/output field.",
        unique=True,
    )
    slug = AutoSlugField(populate_from="title")
    description = models.TextField(
        blank=True, help_text="Description of this input/output field.",
    )
    default_value = models.JSONField(
        null=True,
        default=None,
        help_text="Default value for this field, only valid for inputs.",
    )
    kind = models.CharField(
        blank=False,
        max_length=4,
        choices=Kind.choices,
        help_text=(
            "What is the type of this interface? Used to validate interface "
            "values and connections between components."
        ),
    )
    relative_path = models.CharField(
        max_length=255,
        help_text=(
            "The path to the entity that implements this interface relative "
            "to the input or output directory."
        ),
        unique=True,
        validators=[validate_safe_path],
    )

    def __str__(self):
        return f"Component Interface {self.title} ({self.get_kind_display()})"

    @property
    def input_path(self):
        return safe_join("/input", self.relative_path)

    @property
    def output_path(self):
        return safe_join("/output", self.relative_path)

    class Meta:
        ordering = ("pk",)

    def create_component_interface_values(self, *, reader, job):
        # TODO JM These functions rely on docker specific code (reader)
        if self.kind in (
            InterfaceKindChoices.HEAT_MAP,
            InterfaceKindChoices.IMAGE,
        ):
            self._create_images_result(reader=reader, job=job)

        if self.kind == InterfaceKindChoices.JSON:
            self._create_json_result(reader=reader, job=job)

    def _create_images_result(self, *, reader, job):
        # TODO JM in the future this will be a file, not a directory
        base_dir = Path(self.output_path)
        found_files = reader.exec_run(f"find {base_dir} -type f")

        if found_files.exit_code != 0:
            logger.warning(f"Error listing {base_dir}")
            return

        output_files = [
            base_dir / Path(f)
            for f in found_files.output.decode().splitlines()
        ]

        if not output_files:
            logger.warning("Output directory is empty")
            return

        with TemporaryDirectory() as tmpdir:
            input_files = set()
            for file in output_files:
                temp_file = Path(safe_join(tmpdir, file.relative_to(base_dir)))
                temp_file.parent.mkdir(parents=True, exist_ok=True)

                with open(temp_file, "wb") as outfile:
                    infile = get_file(container=reader, src=file)

                    buffer = True
                    while buffer:
                        buffer = infile.read(1024)
                        outfile.write(buffer)

                input_files.add(temp_file)

            importer_result = import_images(
                files=input_files,
                builders=[image_builder_mhd, image_builder_tiff],
            )

        for image in importer_result.new_images:
            civ = ComponentInterfaceValue.objects.create(
                interface=self, image=image
            )
            job.outputs.add(civ)

    def _create_json_result(self, reader, job):
        try:
            result = get_file(container=reader, src=Path(self.output_path))
        except NotFound:
            # The container exited without error, but no results file was
            # produced. This shouldn't happen, but does with poorly programmed
            # evaluation containers.
            raise ComponentException(
                "The evaluation failed for an unknown reason as no results "
                "file was produced. Please contact the organisers for "
                "assistance."
            )

        try:
            result = json.loads(
                result.read().decode(),
                parse_constant=lambda x: None,  # Removes -inf, inf and NaN
            )
        except JSONDecodeError as e:
            raise ComponentException(f"Could not decode results file: {e.msg}")

        civ = ComponentInterfaceValue.objects.create(
            interface=self, value=result
        )
        job.outputs.add(civ)


def component_interface_value_path(instance, filename):
    # Convert the pk to a hex, padded to 4 chars with zeros
    pk_as_padded_hex = f"{instance.pk:04x}"

    return (
        f"{instance._meta.app_label.lower()}/"
        f"{instance._meta.model_name.lower()}/"
        f"{pk_as_padded_hex[-4:-2]}/{pk_as_padded_hex[-2:]}/{instance.pk}/"
        f"{get_valid_filename(filename)}"
    )


class ComponentInterfaceValue(models.Model):
    """Encapsulates the value of an interface at a certain point in the graph."""

    id = models.BigAutoField(primary_key=True)
    interface = models.ForeignKey(
        to=ComponentInterface, on_delete=models.CASCADE
    )
    value = models.JSONField(null=True, default=None)
    file = models.FileField(
        upload_to=component_interface_value_path, storage=protected_s3_storage
    )
    image = models.ForeignKey(to=Image, null=True, on_delete=models.CASCADE)

    def __str__(self):
        return f"Component Interface Value {self.pk} for {self.interface}"

    class Meta:
        ordering = ("pk",)


class DurationQuerySet(models.QuerySet):
    def with_duration(self):
        """Annotate the queryset with the duration of completed jobs"""
        return self.annotate(duration=F("completed_at") - F("started_at"))

    def average_duration(self):
        """Calculate the average duration that completed jobs ran for"""
        return (
            self.with_duration()
            .exclude(duration=None)
            .aggregate(Avg("duration"))["duration__avg"]
        )


class ComponentJob(models.Model):
    # The job statuses come directly from celery.result.AsyncResult.status:
    # http://docs.celeryproject.org/en/latest/reference/celery.result.html
    PENDING = 0
    STARTED = 1
    RETRY = 2
    FAILURE = 3
    SUCCESS = 4
    CANCELLED = 5

    STATUS_CHOICES = (
        (PENDING, "Queued"),
        (STARTED, "Started"),
        (RETRY, "Re-Queued"),
        (FAILURE, "Failed"),
        (SUCCESS, "Succeeded"),
        (CANCELLED, "Cancelled"),
    )

    status = models.PositiveSmallIntegerField(
        choices=STATUS_CHOICES, default=PENDING
    )
    stdout = models.TextField()
    stderr = models.TextField(default="")
    error_message = models.CharField(max_length=1024, default="")
    started_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)

    inputs = models.ManyToManyField(
        to=ComponentInterfaceValue,
        related_name="%(app_label)s_%(class)ss_as_input",
    )
    outputs = models.ManyToManyField(
        to=ComponentInterfaceValue,
        related_name="%(app_label)s_%(class)ss_as_output",
    )

    objects = DurationQuerySet.as_manager()

    def update_status(
        self,
        *,
        status: STATUS_CHOICES,
        stdout: str = "",
        stderr: str = "",
        error_message="",
    ):
        self.status = status

        if stdout:
            self.stdout = stdout

        if stderr:
            self.stderr = stderr

        if error_message:
            self.error_message = error_message[:1024]

        if status == self.STARTED and self.started_at is None:
            self.started_at = now()
        elif (
            status in [self.SUCCESS, self.FAILURE, self.CANCELLED]
            and self.completed_at is None
        ):
            self.completed_at = now()

        self.save()

    @property
    def container(self) -> "ComponentImage":
        """
        Returns the container object associated with this instance, which
        should be a foreign key to an object that is a subclass of
        ComponentImage
        """
        raise NotImplementedError

    @property
    def input_files(self) -> Tuple[File, ...]:
        """
        Returns a tuple of the input files that will be mounted into the
        container when it is executed
        """
        raise NotImplementedError

    @property
    def output_interfaces(self) -> QuerySet:
        """Returns an unevaluated QuerySet for the output interfaces"""
        raise NotImplementedError

    @property
    def executor_cls(self) -> Type[Executor]:
        """
        Return the executor class for this job.

        The executor class must be a subclass of ``Executor``.
        """
        return Executor

    @property
    def signature(self):
        options = {}

        if self.container.requires_gpu:
            options.update({"queue": "gpu"})

        if getattr(self.container, "queue_override", None):
            options.update({"queue": self.container.queue_override})

        return execute_job.signature(
            kwargs={
                "job_pk": self.pk,
                "job_app_label": self._meta.app_label,
                "job_model_name": self._meta.model_name,
            },
            options=options,
        )

    class Meta:
        abstract = True


def docker_image_path(instance, filename):
    return (
        f"docker/"
        f"images/"
        f"{instance._meta.app_label.lower()}/"
        f"{instance._meta.model_name.lower()}/"
        f"{instance.pk}/"
        f"{get_valid_filename(filename)}"
    )


class ComponentImage(models.Model):
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    staged_image_uuid = models.UUIDField(blank=True, null=True, editable=False)
    image = models.FileField(
        blank=True,
        upload_to=docker_image_path,
        validators=[
            ExtensionValidator(allowed_extensions=(".tar", ".tar.gz"))
        ],
        help_text=(
            ".tar.gz archive of the container image produced from the command "
            "'docker save IMAGE | gzip -c > IMAGE.tar.gz'. See "
            "https://docs.docker.com/engine/reference/commandline/save/"
        ),
        storage=private_s3_storage,
    )

    image_sha256 = models.CharField(editable=False, max_length=71)

    ready = models.BooleanField(
        default=False,
        editable=False,
        help_text="Is this image ready to be used?",
    )
    status = models.TextField(editable=False)

    requires_gpu = models.BooleanField(default=False)
    requires_gpu_memory_gb = models.PositiveIntegerField(default=4)
    requires_memory_gb = models.PositiveIntegerField(default=4)
    # Support up to 99.99 cpu cores
    requires_cpu_cores = models.DecimalField(
        default=Decimal("1.0"), max_digits=4, decimal_places=2
    )

    def save(self, *args, **kwargs):
        adding = self._state.adding

        super().save(*args, **kwargs)

        if adding:
            validate_docker_image.apply_async(
                kwargs={
                    "app_label": self._meta.app_label,
                    "model_name": self._meta.model_name,
                    "pk": self.pk,
                }
            )

    class Meta:
        abstract = True
