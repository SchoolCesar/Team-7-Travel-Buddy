# Travel Buddy - Find your Perfect Travel Companion

A student travel service that allows students to post prospective travel plans and the option to connect with others to join them.

## Models

### Student
Represents verified university students. Email verification ensures campus safety.

- **Key Constraint**: Unique university email
- **Ordering**: Newest registrations first

### Category
Organizes listings by geography.

- **Key Constraint**: Unique name per category type
- **Ordering**: Alphabetical

### Listing
Student-posted potential travel plans.

- **Key Relationships**:
  - ForeignKey to Student (CASCADE) - If student leaves, their listings should too
  - ForeignKey to Category (PROTECT) - Can't delete categories with active listings
- **Key Constraint**: Student can't create duplicate listing titles
- **Ordering**: Newest listings first


## Dependencies

annotated-doc==0.0.4
anyio==4.12.1
asgiref
bleach==6.3.0
Brotli
brotlicffi
certifi
cffi
charset-normalizer
click==8.3.1
contourpy
cryptography
cycler
Django
django-allauth==65.14.3
filelock==3.25.0
fonttools
fsspec==2026.2.0
gunicorn==23.0.0
h11==0.16.0
hf-xet==1.3.2
httpcore==1.0.9
httpx==0.28.1
huggingface_hub==1.6.0
idna
Jinja2==3.1.6
kiwisolver
markdown-it-py==4.0.0
MarkupSafe==3.0.3
matplotlib==3.10.0
mdurl==0.1.2
mpmath==1.3.0
networkx==3.6.1
numpy
packaging
pillow
pycparser
Pygments==2.19.2
PyJWT
pyparsing
PySocks
python-dateutil
python-decouple==3.8
PyYAML==6.0.3
regex==2026.2.28
requests
rich==14.3.3
scikit-learn==1.7.2
safetensors==0.7.0
shellingham==1.5.4
six
sqlparse
sympy>=1.13.1
tokenizers==0.22.2
torch==2.6.0
tornado
tqdm==4.67.3
transformers==5.3.0
typer==0.24.1
typing_extensions==4.15.0
unicodedata2
urllib3
webencodings==0.5.1
whitenoise==6.11.0


## Setup Instructions

1. Create superuser: `python manage.py createsuperuser`
   - Username: tester
   - Password: uiuc12345

2. Run server: `python manage.py runserver`

3. Access admin: http://127.0.0.1:8000/admin/


## API Description
This project provides a public API to allow external applications to access and filter listing data.

1. Active Listings Data Endpoint
   - URL Path: /api/listings/
   - Method: GET
   - Format: JSON
   - Data Fields Provided:
     - Title: name of the listing
     - Price: cost of the travel 
     - Category: the locations, start and end point

## AI Location

To access the AI in this app you have to navigate to the "Post a Trip" link that is located at the top with the navbar
