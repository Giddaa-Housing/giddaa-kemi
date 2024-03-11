import json
import os

import requests
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from verification.models import EmploymentVerification
from verification.pdf.analyze import get_pdf_category
from verification.tasks import process_pdf_task
from verification.verifications import birth_certificate, employee_letter


class VerifyAgeView(APIView):
    def get(self, request, document_id):
        result = birth_certificate(document_id)
        return Response({"result": result})


class VerifyEmployeeLetterView(APIView):
    def get(self, request, document_id):
        employee_letter_result = employee_letter(document_id)
        return Response({"result": employee_letter_result})


def confirm_employment(request):
    token = request.GET.get("token")
    CALLBACK_URL = os.environ.get("CALLBACK_URL", "")
    try:
        verification = EmploymentVerification.objects.get(token=token)
        verification.is_verified = True
        verification.verified_at = timezone.now()  # Manually set when verified
        verification.save()

        response_data = {"status": "confirmed", "token": token}
        requests.post(CALLBACK_URL, data=response_data)

        return HttpResponse("Employment confirmed.")
    except EmploymentVerification.DoesNotExist:
        return HttpResponse("Invalid token.")


def deny_employment(request):
    token = request.GET.get("token")
    CALLBACK_URL = os.environ.get("CALLBACK_URL", "")
    try:
        verification = EmploymentVerification.objects.get(token=token)
        verification.is_verified = False
        verification.save()

        response_data = {"status": "denied", "token": token}
        requests.post(CALLBACK_URL, data=response_data)

        return HttpResponse("Employment denied.")
    except EmploymentVerification.DoesNotExist:
        return HttpResponse("Invalid token.")


def get_employment_verification_info(request, token):
    try:
        employment_verification = EmploymentVerification.objects.get(token=token)
        data = {
            "token": employment_verification.token,
            "status": employment_verification.status,
            "is_verified": employment_verification.is_verified,
            "verified_at": (
                employment_verification.verified_at.strftime("%Y-%m-%d %H:%M:%S")
                if employment_verification.verified_at
                else None
            ),
        }
        return JsonResponse(data)
    except EmploymentVerification.DoesNotExist:
        return JsonResponse({"error": "Token not found"}, status=404)


# # class ScraperView(APIView):
# #     def get(self, request, *args, **kwargs):

# #         # scraper()
# #         url="https://www.enricodeiana.design/"
# #         scrape_website(url)

# #         return JsonResponse({"done": "done"})


# class ApolloView(APIView):
#     def get(self, request, *args, **kwargs):
#         url = "https://www.zenithbank.com/"
#         url = "https://www.enricodeiana.design/"
#         data = get_website_rep_details(url)
#         return JsonResponse({"data": data})


class BankStatementView(View):
    def get(self, request, document_id):
        # public_url = "https://res.cloudinary.com/giddaa/image/upload/c_scale,w_1000/q_auto:good/133512587437717390.pdf"

        # Process the URL as before
        pdf_type, public_url = get_pdf_category(document_id)

        if pdf_type in [1, 2]:
            result = process_pdf_task.apply(args=[pdf_type, public_url]).get()
            return JsonResponse({"status": "completed", "result": result})
        elif pdf_type == 3:
            process_pdf_task.delay(pdf_type, public_url)
            return JsonResponse(
                {
                    "status": "Analysis on this PDF would take about 60 secs so please check back"
                }
            )

        return JsonResponse({"error": "Invalid PDF type"}, status=400)
