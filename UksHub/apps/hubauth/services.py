from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User

from UksHub.apps.hub.models import UserProfile


def loginUser(request, username, password):
    user = authenticate(username=username, password=password)
    if user is None:
        return False
    else:
        login(request, user)
        return True


def logoutUser(request):
    logout(request)


def createUser(request, registerForm):
    user = User.objects.create_user(
        registerForm.cleaned_data['username'], registerForm.cleaned_data['email'], registerForm.cleaned_data['password'])
    UserProfile.objects.create(user=user)
    return loginUser(request,
                     registerForm.cleaned_data['username'], registerForm.cleaned_data['password'])
