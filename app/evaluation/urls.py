from django.conf.urls import url, include
from rest_framework import routers
from rest_framework.authtoken.views import obtain_auth_token

from evaluation.views import ResultViewSet, SubmissionViewSet, JobViewSet, \
    MethodViewSet, uploader_mock

router = routers.DefaultRouter()
router.register(r'results', ResultViewSet)
router.register(r'submissions', SubmissionViewSet)
router.register(r'jobs', JobViewSet)
router.register(r'methods', MethodViewSet)

urlpatterns = [
    url(r'^api/v1/', include(router.urls)),
    url(r'^api-auth/', include('rest_framework.urls',
                               namespace='rest_framework')),
    url(r'^api-token-auth/', obtain_auth_token),
    url(r'^test', uploader_mock)
]
