import datetime
import json
import os
import uuid
from smtplib import SMTPServerDisconnected
from urllib.parse import urlparse

import openai
import requests
from decouple import config
from django.conf import settings
from django.core.mail import send_mail
from django.db import connections
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import OnlinePDFLoader

from bankanalysis.configs.logging_config import configure_logger
from helpers import chat_utils
from verification.models import EmploymentVerification

logger = configure_logger(__name__)


SYSTEM_ROLE = "system"
USER_ROLE = "user"


BASE_URL = settings.APP_BASE_URL


def create_openai_request(model, messages, functions, function_name, function_args):
    return openai.ChatCompletion.create(
        model=model,
        messages=messages,
        functions=functions,
        function_call={"name": function_name, "arguments": json.dumps(function_args)},
    )


def handle_openai_response(response):
    response_message = response["choices"][0]["message"]
    if response_message.get("function_call"):
        return json.loads(response_message["function_call"]["arguments"])
    return None


def extract_domain_from_url(url):
    """
    Extract the domain from a given URL. Removes 'www.' prefix if present.
    """
    parsed_url = urlparse(url)
    domain = parsed_url.netloc or url
    return domain.lstrip("www.")


def get_document_file_by_id(document_id):
    try:
        with connections["giddaa_db"].cursor() as cursor:
            # cursor.execute('SELECT "Document" FROM "public"."Documents" WHERE "Id" = %s', [document_id])
            # cursor.execute('SELECT * FROM "public"."Documents" WHERE "Id" = %s', [document_id])
            cursor.execute(
                'SELECT "Id", "Name", "Description", "Extension", "Document", "CloudinaryLink", "ExtraProperties" FROM "public"."Documents" WHERE "Id" = %s',
                [document_id],
            )

            row = cursor.fetchone()
            if row:
                # Assuming columns are id, name, description, extension, document, extraProperties
                document_data = {
                    "id": row[0],
                    "name": row[1],
                    "description": row[2],
                    "extension": row[3],
                    "document": row[4],
                    "cloudinary_link": row[5],
                    "extraProperties": row[6],
                }
                logger.info(f"-------------- DOCUMENT DATA: --------------")
                logger.info(f"{document_data}")
                return document_data
            else:
                return None
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        return None


def extract_apollo_data(apollo_response):
    """
    Extract relevant details from the Apollo API response.
    """
    person = apollo_response["people"][0]
    organization = person["organization"]

    return {
        "first_name": person["first_name"],
        "last_name": person["last_name"],
        "full_name": person["name"],
        "linkedin_url": person["linkedin_url"],
        "title": person["title"],
        "email": person["email"],
        "organization_name": organization["name"],
        "organization_website_url": organization["website_url"],
        "organization_primary_phone": organization["primary_phone"],
        "organization_phone": organization["phone"],
    }


def send_verification_email(subject, message, recipient_list):
    try:
        send_mail(
            subject=subject,
            message="",
            html_message=message,
            recipient_list=recipient_list,
            from_email=settings.DEFAULT_FROM_EMAIL,
        )
    except SMTPServerDisconnected:
        logger.warning("Failed to send email: SMTP server disconnected")
    except Exception as e:
        logger.error(f"An error occurred: {e}")


def get_website_rep_details(company_website_url):
    """
    Fetch representative details for a given company website URL using the Apollo API.
    """
    API_URL = "https://api.apollo.io/v1/mixed_people/search"
    domain = extract_domain_from_url(company_website_url)

    data = {
        "api_key": os.getenv("APOLLO_API_TOKEN"),
        "q_organization_domains": domain,
        "page": 1,
        "person_titles": ["HR", "Admin"],
    }

    headers = {"Cache-Control": "no-cache", "Content-Type": "application/json"}

    response = requests.post(API_URL, headers=headers, json=data)
    if response.status_code != 200:
        logger.error(
            f"API request failed with status code {response.status_code}. Reason: {response.text}"
        )
        return None

    apollo_data = json.loads(response.text)
    extracted_data = extract_apollo_data(apollo_data)

    # logger.info(f"EXTRACTED DATA: {extracted_data}")

    return extracted_data


def birth_certificate(document_id):
    document_data = get_document_file_by_id(document_id)
    public_url = document_data["cloudinary_link"]

    # Load PDF data
    loader = OnlinePDFLoader(public_url)
    data = loader.load()
    # from langchain.document_loaders import UnstructuredPDFLoader
    # loader = UnstructuredPDFLoader("docanalysis/bc.pdf")
    # data = loader.load()

    # Split the text for analysis
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=0)
    texts = text_splitter.split_documents(data)

    birth_certificate_list = [t.page_content for t in texts]
    birth_certificate = "   ".join(birth_certificate_list)

    messages = [
        {
            "role": SYSTEM_ROLE,
            "content": chat_utils.BIRTH_CERTIFICATE_VERIFICATION_INSTRUCTION,
        },
        {"role": USER_ROLE, "content": birth_certificate},
    ]

    response = create_openai_request(
        model="gpt-4-1106-preview",
        messages=messages,
        functions=chat_utils.BIRTH_CERTIFICATE_FUNCTIONS_PARAMS,
        function_name="get_birth_certificate_entities",
        function_args={},
    )

    birth_certificate_entities = handle_openai_response(response)

    # Extracting birth date details
    birth_date = int(birth_certificate_entities.get("birth_date", 1))
    birth_month = birth_certificate_entities.get("birth_month", "January")
    birth_year = int(birth_certificate_entities.get("birth_year", 2000))

    # Convert the birth month to a numeric value
    month_number = datetime.datetime.strptime(birth_month, "%B").month

    # Create a datetime object for the birth date
    birth_datetime = datetime.datetime(birth_year, month_number, birth_date)

    # Get the current date
    current_datetime = datetime.datetime.now()

    # Calculate the age
    age = (
        current_datetime.year
        - birth_datetime.year
        - (
            (current_datetime.month, current_datetime.day)
            < (birth_datetime.month, birth_datetime.day)
        )
    )

    # Add the age to the birth_certificate_entities dictionary
    birth_certificate_entities["age"] = age

    logger.info(f"---------------- EMPLOYEE LETTER ENTITIES: ----------------")
    logger.info(f"{birth_certificate_entities}")

    return birth_certificate_entities


def employee_letter(document_id):
    # Upload PDF to Google Cloud Storage and get the public URL
    # public_url, blob = write_file_to_gcp_storage(pdf_id)
    document_data = get_document_file_by_id(document_id)
    public_url = document_data["cloudinary_link"]
    extra_properties = document_data["extraProperties"]

    try:
        extra_properties = extra_properties.replace('\\"', '"').replace("\\'", "'")
        extra_properties_dict = json.loads(extra_properties)
        print("This is the extra properties dict", extra_properties_dict)

        # Accessing the organization website
        organization_website = extra_properties_dict.get("website_url", "Not Available")

        logger.info(f"------------------ ORGANIZATION WEBSITE: ------------------")
        logger.info(f"{organization_website}")
        rep_data = get_website_rep_details(organization_website)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse extra properties JSON: {e}")
        logger.info("No Extra properties given!")

    # Load PDF data
    loader = OnlinePDFLoader(public_url)
    data = loader.load()
    # from langchain.document_loaders import UnstructuredPDFLoader
    # loader = UnstructuredPDFLoader("docanalysis/letter.pdf")
    # data = loader.load()

    # Split the text for analysis
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=0)
    texts = text_splitter.split_documents(data)

    employee_letter_list = [t.page_content for t in texts]
    employee_letter = "   ".join(employee_letter_list)

    # applicant = OrganizationCustomer.objects.get(id=applicant_id)

    # Generate a unique token for this verification
    unique_token = uuid.uuid4().hex

    messages = [
        {
            "role": SYSTEM_ROLE,
            "content": chat_utils.EMPLOYMENT_VERIFICATION_INSTRUCTION,
        },
        {"role": USER_ROLE, "content": employee_letter},
    ]

    response = create_openai_request(
        model="gpt-4-1106-preview",
        messages=messages,
        functions=chat_utils.EMPLOYMENT_LETTER_FUNCTIONS_PARAMS,
        function_name="get_employment_letter_entities",
        function_args={},
    )

    employee_letter_entities = handle_openai_response(response)

    logger.info(f"---------------- EMPLOYEE LETTER ENTITIES: ----------------")
    logger.info(f"{employee_letter_entities}")

    restructured_data = {
        "employee_letter_token": unique_token,
        "employment_date": employee_letter_entities.get("start_date", None),
        "current_staff": employee_letter_entities.get("current_staff", None),
        "job_role": employee_letter_entities.get("job_role", None),
        "salary": employee_letter_entities.get("salary", None),
        "company_name": employee_letter_entities.get("company_name", None),
        "company_website": employee_letter_entities.get("company_website", None),
        "sources": {
            "employment_letter_representative": {
                "representative": employee_letter_entities.get("representative", None),
                "representative_position": employee_letter_entities.get(
                    "representative_position", None
                ),
                "representative_email": employee_letter_entities.get(
                    "representative_email", None
                ),
                "representative_phone_number": employee_letter_entities.get(
                    "representative_phone_number", None
                ),
            }
        },
    }

    if rep_data:
        restructured_data["sources"]["apollo_representative"] = {
            "first_name": rep_data["first_name"],
            "last_name": rep_data["last_name"],
            "full_name": rep_data["full_name"],
            "linkedin_url": rep_data["linkedin_url"],
            "title": rep_data["title"],
            "email": rep_data["email"],
            "organization_name": rep_data["organization_name"],
            "organization_website_url": rep_data["organization_website_url"],
            "organization_phone": rep_data["organization_phone"],
            "organization_primary_phone": {
                "number": rep_data["organization_primary_phone"]["number"],
                "source": rep_data["organization_primary_phone"]["source"],
            },
        }

    # Put it back on if need be
    # if organization_website:
    #     organization_website = "https://www.enricodeiana.design/"
    #     website_email_details = scrape_website(organization_website)
    #     website_email_details = website_email_details['email_list'][0]
    #     logger.info(website_email_details)
    #     restructured_data["sources"]["from_web_representative"] = {
    #         'email': website_email_details.get('email', None),
    #         'role': website_email_details.get('role', None),
    #     }

    # Check if all values in the 'sources' key are None
    if all(value is None for value in restructured_data["sources"].values()):
        restructured_data["sources"] = (
            "We could not find any source to verify the applicant’s employment"
        )

    # Save the token and other details to the database
    EmploymentVerification.objects.create(
        token=unique_token,
        status="pending",
        is_verified=False,
        verification_data=restructured_data,
    )

    confirmation_url = (
        BASE_URL + f"/api/verify/confirm-employment/?token={unique_token}"
    )
    denial_url = BASE_URL + f"/api/verify/deny-employment/?token={unique_token}"

    subject = "Employee Confirmation"
    message = f"""
        An employee at your organization, {employee_letter_entities.get('employee_name', None)}, has applied to receive a mortgage through our platform. This message is being sent to you to confirm their employment status at your organization.<br><br>
        Click <a href='{confirmation_url}'>Yes, they work here</a> if they currently work at your organization.<br><br>
        Click <a href='{denial_url}'>No, they don't work here</a> if they don't.<br><br>
        If you are not the appropriate person to confirm this information, please forward this email to your Human Resources department or the appropriate person within your organization.<br><br>
        Thank you for your prompt attention to this matter.
    """

    organization_rep_email = rep_data["email"]
    # organization_rep_email = "danielnwachukwu5738@gmail.com"  # testing
    recipient_list = [organization_rep_email]
    send_verification_email(subject, message, recipient_list)

    logger.info(f"---------------- FINAL DATA: ----------------")
    logger.info(restructured_data)

    return restructured_data
