from django.db.models import Count
from firebase_admin.auth import delete_user
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from blabhear.models import User, Room


class DeleteAccountView(APIView):
    def delete(self, request):
        try:
            delete_user(request.user.username)
        except Exception:
            pass
        User.objects.filter(username=request.user.username).delete()
        Room.objects.annotate(num_members=Count("members")).filter(
            num_members=1
        ).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
