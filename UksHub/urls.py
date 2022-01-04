from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from UksHub.apps.hubAuth.urls import urlpatterns as authUrls
from UksHub.apps.gitcore.urls import urlpatterns as gitCoreUrls

urlpatterns = []

if settings.ADMIN_ENABLED is True:
    urlpatterns += [path('admin/', admin.site.urls)]

urlpatterns += [
    path('backoffice/', include('UksHub.apps.backoffice.urls')),
    *authUrls,
    *gitCoreUrls,
    path('', include('UksHub.apps.hub.urls'))
]
