# hospital-delirium-alert

# Runtime requirements

## install dependencies
`pip install -r requirements.txt`

## create a .env file with your credentials
edit .env with your MongoDB URI
cp .env.example .env

# run
`python -m uvicorn main:app --reload`