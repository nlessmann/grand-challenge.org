import csv
import re

from dal import autocomplete
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import (
    PermissionRequiredMixin,
    UserPassesTestMixin,
)
from django.contrib.messages.views import SuccessMessageMixin
from django.http import Http404, HttpResponse
from django.views.generic import (
    CreateView,
    DetailView,
    FormView,
    ListView,
    UpdateView,
)
from guardian.mixins import (
    LoginRequiredMixin,
    PermissionListMixin,
    PermissionRequiredMixin as ObjectPermissionRequiredMixin,
)
from rest_framework.decorators import action
from rest_framework.mixins import (
    CreateModelMixin,
    ListModelMixin,
    RetrieveModelMixin,
)
from rest_framework.permissions import DjangoObjectPermissions
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet, ReadOnlyModelViewSet
from rest_framework_guardian.filters import ObjectPermissionsFilter

from grandchallenge.cases.forms import UploadRawImagesForm
from grandchallenge.cases.models import RawImageUploadSession
from grandchallenge.reader_studies.forms import (
    EditorsForm,
    QuestionForm,
    ReaderStudyCreateForm,
    ReaderStudyUpdateForm,
    ReadersForm,
)
from grandchallenge.reader_studies.models import Answer, Question, ReaderStudy
from grandchallenge.reader_studies.serializers import (
    AnswerSerializer,
    QuestionSerializer,
    ReaderStudySerializer,
)


class ReaderStudyList(LoginRequiredMixin, PermissionListMixin, ListView):
    model = ReaderStudy
    permission_required = (
        f"{ReaderStudy._meta.app_label}.view_{ReaderStudy._meta.model_name}"
    )


class ReaderStudyCreate(
    LoginRequiredMixin, PermissionRequiredMixin, CreateView
):
    model = ReaderStudy
    form_class = ReaderStudyCreateForm
    permission_required = (
        f"{ReaderStudy._meta.app_label}.add_{ReaderStudy._meta.model_name}"
    )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        self.object.add_editor(self.request.user)
        return response


class ReaderStudyDetail(
    LoginRequiredMixin, ObjectPermissionRequiredMixin, DetailView
):
    model = ReaderStudy
    permission_required = (
        f"{ReaderStudy._meta.app_label}.view_{ReaderStudy._meta.model_name}"
    )
    raise_exception = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {"user_is_reader": self.object.is_reader(user=self.request.user)}
        )
        return context


class ReaderStudyUpdate(
    LoginRequiredMixin, ObjectPermissionRequiredMixin, UpdateView
):
    model = ReaderStudy
    form_class = ReaderStudyUpdateForm
    permission_required = (
        f"{ReaderStudy._meta.app_label}.change_{ReaderStudy._meta.model_name}"
    )
    raise_exception = True

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs


class QuestionUpdate(
    LoginRequiredMixin, ObjectPermissionRequiredMixin, UpdateView
):
    model = Question
    form_class = QuestionForm
    template_name = "reader_studies/readerstudy_update_object.html"
    permission_required = (
        f"{ReaderStudy._meta.app_label}.change_{ReaderStudy._meta.model_name}"
    )
    raise_exception = True

    def get_permission_object(self):
        return self.reader_study

    @property
    def reader_study(self):
        return ReaderStudy.objects.get(slug=self.kwargs["slug"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form_fields = context["form"].fields
        for field_name in self.object.read_only_fields:
            form_fields[field_name].required = False
            form_fields[field_name].disabled = True

        return context

    def get_success_url(self):
        return self.object.reader_study.get_absolute_url()


class AddObjectToReaderStudyMixin(
    LoginRequiredMixin, ObjectPermissionRequiredMixin, CreateView
):
    """
    Mixin that adds an object that has a foreign key to a reader study and a
    creator. The url to this view must include a slug that points to the slug
    of the reader study.

    Must be placed to the left of ObjectPermissionRequiredMixin.
    """

    permission_required = (
        f"{ReaderStudy._meta.app_label}.change_{ReaderStudy._meta.model_name}"
    )
    raise_exception = True

    def get_permission_object(self):
        return self.reader_study

    @property
    def reader_study(self):
        return ReaderStudy.objects.get(slug=self.kwargs["slug"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {"object": self.reader_study, "type_to_add": self.type_to_add}
        )
        return context

    def form_valid(self, form):
        form.instance.creator = self.request.user
        form.instance.reader_study = self.reader_study
        return super().form_valid(form)

    def get_success_url(self):
        return self.object.reader_study.get_absolute_url()


class AddImagesToReaderStudy(AddObjectToReaderStudyMixin):
    model = RawImageUploadSession
    form_class = UploadRawImagesForm
    template_name = "reader_studies/readerstudy_add_object.html"
    type_to_add = "images"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs


class AddQuestionToReaderStudy(AddObjectToReaderStudyMixin):
    model = Question
    form_class = QuestionForm
    template_name = "reader_studies/readerstudy_add_object.html"
    type_to_add = "question"


class ReaderStudyUserAutocomplete(
    LoginRequiredMixin, UserPassesTestMixin, autocomplete.Select2QuerySetView
):
    def test_func(self):
        group_pks = (
            ReaderStudy.objects.all()
            .select_related("editors_group")
            .values_list("editors_group__pk", flat=True)
        )
        return (
            self.request.user.is_superuser
            or self.request.user.groups.filter(pk__in=group_pks).exists()
        )

    def get_queryset(self):
        qs = (
            get_user_model()
            .objects.all()
            .order_by("username")
            .exclude(username=settings.ANONYMOUS_USER_NAME)
        )

        if self.q:
            qs = qs.filter(username__istartswith=self.q)

        return qs


class ReaderStudyUserGroupUpdateMixin(
    LoginRequiredMixin,
    ObjectPermissionRequiredMixin,
    SuccessMessageMixin,
    FormView,
):
    template_name = "reader_studies/readerstudy_user_groups_form.html"
    permission_required = (
        f"{ReaderStudy._meta.app_label}.change_{ReaderStudy._meta.model_name}"
    )
    raise_exception = True

    def get_permission_object(self):
        return self.reader_study

    @property
    def reader_study(self):
        return ReaderStudy.objects.get(slug=self.kwargs["slug"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {"object": self.reader_study, "role": self.get_form().role}
        )
        return context

    def get_success_url(self):
        return self.reader_study.get_absolute_url()

    def form_valid(self, form):
        form.add_or_remove_user(reader_study=self.reader_study)
        return super().form_valid(form)


class EditorsUpdate(ReaderStudyUserGroupUpdateMixin):
    form_class = EditorsForm
    success_message = "Editors successfully updated"


class ReadersUpdate(ReaderStudyUserGroupUpdateMixin):
    form_class = ReadersForm
    success_message = "Readers successfully updated"


class ExportCSVMixin(object):
    def _check_export_perms(self, user, obj):
        if not (user and user.has_perm(self.export_permission, obj)):
            raise Http404()

    def _create_dicts(self, headers, data):
        return map(lambda x: dict(zip(headers, x)), data)

    def _preprocess_data(self, data):
        processed = []
        for entry in data:
            processed.append(
                map(lambda x: re.sub(r"[\n\r\t]", " ", str(x)), entry)
            )
        return processed

    def _create_csv_response(self, data, headers, filename="export.csv"):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        writer = csv.DictWriter(
            response,
            quoting=csv.QUOTE_ALL,
            escapechar="\\",
            fieldnames=headers,
        )
        writer.writeheader()
        csv_dict = self._create_dicts(headers, self._preprocess_data(data))
        writer.writerows(csv_dict)

        return response


class ReaderStudyViewSet(ExportCSVMixin, ReadOnlyModelViewSet):
    serializer_class = ReaderStudySerializer
    queryset = ReaderStudy.objects.all().prefetch_related(
        "images", "questions"
    )
    permission_classes = [DjangoObjectPermissions]
    filter_backends = [ObjectPermissionsFilter]
    export_permission = (
        f"{ReaderStudy._meta.app_label}.change_{ReaderStudy._meta.model_name}"
    )

    @action(detail=True)
    def export_answers(self, request, pk=None):
        reader_study = self.get_object()
        self._check_export_perms(request.user, reader_study)

        data = [
            answer.csv_values
            for answer in Answer.objects.select_related(
                "question__reader_study"
            )
            .select_related("creator")
            .prefetch_related("images")
            .filter(question__reader_study=reader_study)
        ]

        return self._create_csv_response(
            data,
            Answer.csv_headers,
            filename=f"{reader_study.slug}-answers.csv",
        )


class QuestionViewSet(ReadOnlyModelViewSet):
    serializer_class = QuestionSerializer
    queryset = Question.objects.all().select_related("reader_study")
    permission_classes = [DjangoObjectPermissions]
    filter_backends = [ObjectPermissionsFilter]


class AnswerViewSet(
    CreateModelMixin, RetrieveModelMixin, ListModelMixin, GenericViewSet
):
    serializer_class = AnswerSerializer
    queryset = (
        Answer.objects.all()
        .select_related("creator")
        .prefetch_related("images")
    )
    permission_classes = [DjangoObjectPermissions]
    filter_backends = [ObjectPermissionsFilter]

    def perform_create(self, serializer):
        serializer.save(creator=self.request.user)

    @action(detail=False)
    def mine(self, request):
        """
        An endpoint that returns the questions that have been answered by
        the current user.
        """
        queryset = self.filter_queryset(
            self.get_queryset().filter(creator=request.user)
        )

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
