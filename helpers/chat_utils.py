BIRTH_CERTIFICATE_VERIFICATION_INSTRUCTION = """
    You are a help assistant that helps get the required entities from an birth certificate.
"""


BIRTH_CERTIFICATE_FUNCTIONS_PARAMS = [
    {
        "name": "get_birth_certificate_entities",
        "description": "Extracts specified entities from the provided birth certificate content. If a specified entity is not found in the birth certificate, the function returns 'None' for that entity.",
        "parameters": {
            "type": "object",
            "properties": {
                "birth_date": {
                    "type": "string",
                    "description": "The day of birth of the individual as mentioned in the birth certificate.",
                },
                "birth_month": {
                    "type": "string",
                    "description": "The month of birth of the individual as mentioned in the birth certificate.",
                },
                "birth_year": {
                    "type": "string",
                    "description": "The year of birth of the individual as mentioned in the birth certificate.",
                },
                "birth_state": {
                    "type": "string",
                    "description": "The state of birth of the individual as mentioned in the birth certificate.",
                },
                "birth_country": {
                    "type": "string",
                    "description": "The country of birth of the individual as mentioned in the birth certificate.",
                },
            },
        },
    }
]
