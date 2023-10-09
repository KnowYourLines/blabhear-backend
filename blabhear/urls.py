from django.urls import path

from blabhear import views

urlpatterns = [
    path(r"account", views.DeleteAccountView.as_view()),
]
