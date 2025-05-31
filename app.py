from flask import Flask, request, render_template
import requests
import openai
import os
from datetime import datetime
from weasyprint import HTML
import sendgrid
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
import base64
import traceback

app = Flask(__name__)

AIRTABLE_TOKEN = os.getenv("AIRTABLE_TOKEN")
BASE_ID = "appShV6ffCc9yxeHF"
TABLE_NAME = "Properties"
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
openai.api_key = os.getenv("OPENAI_API_KEY")

def get_coordinates_from_postcode(postcode):
    print("[DEBUG] Getting coordinates for postcode:", postcode)
    url = f"https://api.postcodes.io/postcodes/{postcode}"
    response = requests.get(url)
    if response.status_code == 200:
        result = response.json()["result"]
        return result["latitude"], result["longitude"]
    return None, None

def generate_ai_estimate(postcode, bedrooms, bathrooms, sqft):
    print("[DEBUG] Generating AI estimate")
    prompt = f"Estimate the UK property value for a {sqft} sq ft, {bedrooms}-bedroom, {bathrooms}-bathroom house in {postcode}. Return a number in GBP."
    response = openai.Completion.create(
        engine="text-davinci-003",
        prompt=prompt,
        max_tokens=20
    )
    estimate = response.choices[0].text.strip().replace(",", "").replace("£", "")
    print("[DEBUG] AI Estimate:", estimate)
    return int(float(estimate))

def send_to_airtable(data):
    print("[DEBUG] Sending data to Airtable")
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_TOKEN}",
        "Content-Type": "application/json"
    }
    airtable_data = {
        "fields": {
            "Email": data.get("email"),
            "Postcode": data.get("postcode"),
            "Bedrooms": data.get("bedrooms"),
            "Bathrooms": data.get("bathrooms"),
            "SqFt": data.get("sqft"),
            "Last Sold Price": data.get("last_sold"),
            "AI Estimate": data.get("ai_estimate"),
            "Confidence Score": data.get("confidence"),
            "Latitude": data.get("latitude"),
            "Longitude": data.get("longitude"),
            "Valuation Date": datetime.now().isoformat()
        }
    }
    response = requests.post(url, json=airtable_data, headers=headers)
    print("[DEBUG] Airtable response:", response.status_code, response.text)

def generate_pdf(data):
    print("[DEBUG] Generating PDF")
    html = render_template("pdf_template.html", data=data)
    pdf = HTML(string=html).write_pdf()
    print("[DEBUG] PDF generation complete")
    return pdf

def send_email_with_pdf(to_email, pdf_data, data):
    print("[DEBUG] Sending email to", to_email)
    sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
    encoded_pdf = base64.b64encode(pdf_data).decode()
    message = Mail(
        from_email="no-reply@trueval.ai",
        to_emails=to_email,
        subject="Your Property Valuation Report",
        html_content=f"<p>Hi, your property at {data['postcode']} is valued at £{data['ai_estimate']}</p>"
    )
    attachment = Attachment()
    attachment.file_content = FileContent(encoded_pdf)
    attachment.file_type = FileType("application/pdf")
    attachment.file_name = FileName("valuation.pdf")
    attachment.disposition = Disposition("attachment")
    message.attachment = attachment
    response = sg.send(message)
    print("[DEBUG] Email sent. Response code:", response.status_code)

@app.route("/", methods=["GET"])
def index():
    return render_template("form.html")

@app.route("/submit", methods=["POST"])
def submit_property():
    try:
        print("[DEBUG] Received form submission")
        data = request.form.to_dict()
        data["bedrooms"] = int(data["bedrooms"])
        data["bathrooms"] = int(data["bathrooms"])
        data["sqft"] = int(data["sqft"])
        data["last_sold"] = int(data["last_sold"])
        data["ai_estimate"] = generate_ai_estimate(data["postcode"], data["bedrooms"], data["bathrooms"], data["sqft"])
        data["confidence"] = 90

        lat, lon = get_coordinates_from_postcode(data["postcode"])
        data["latitude"] = lat
        data["longitude"] = lon

        send_to_airtable(data)

        pdf_data = generate_pdf(data)
        send_email_with_pdf(data["email"], pdf_data, data)

        return render_template("map.html", postcode=data["postcode"], ai_value=data["ai_estimate"], latitude=lat, longitude=lon)
    except Exception as e:
        print("[ERROR] An error occurred:", str(e))
        traceback.print_exc()
        return "Internal Server Error", 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
