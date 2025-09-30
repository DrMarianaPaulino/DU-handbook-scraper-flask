from flask import Flask, render_template, request, send_file, Response
import pandas as pd
import requests
from bs4 import BeautifulSoup
import os
import re
from io import BytesIO
import time
import threading

app = Flask(__name__)

progress_messages = []
final_output = None

def create_unit_template():
    return {
        "Unit Code": "", "Unit Name": "", "Offering information": "", "Enrolment modes": "",
        "Credit Points": "", "EFTSL value": "", "Previously coded as": "", "Assumed Knowledge": "",
        "Unit Chair Trimester 1": "", "Unit Chair Trimester 2": "", "Unit Chair Trimester 3": "",
        "Prerequisite": "", "Corequisite": "", "Incompatible with": "",
        "Learning activities - On-campus enrolment": "", "Learning activities - Online enrolment": "",
        "Typical study commitment": "", "Content": "", "Hurdle requirement": "", "Learning resource": ""
    }

def normalize_unit_data(data):
    for unit in data:
        for i in range(1, 9):
            unit.setdefault(f"ULO{i} Description", "")
            unit.setdefault(f"ULO{i} GLO Alignment", "")
        for i in range(1, 7):
            unit.setdefault(f"Assessment {i} Description", "")
            unit.setdefault(f"Assessment {i} Student output", "")
            unit.setdefault(f"Assessment {i} Grading", "")
            unit.setdefault(f"Assessment {i} Indicative due week", "")
    return data

custom_order = [
    "Unit Code", "Unit Name", "Offering information", "Enrolment modes",
    "Credit Points", "EFTSL value", "Previously coded as", "Assumed Knowledge",
    "Unit Chair Trimester 1", "Unit Chair Trimester 2", "Unit Chair Trimester 3",
    "Prerequisite", "Corequisite", "Incompatible with",
    "Learning activities - On-campus enrolment", "Learning activities - Online enrolment",
    "Typical study commitment", "Content", "Hurdle requirement", "Learning resource"
]

# Add ULOs 1–8
for i in range(1, 9):
    custom_order += [
        f"ULO{i} Description", f"ULO{i} GLO Alignment"
    ]

# Add Assessments 1–6
for i in range(1, 7):
    custom_order += [
        f"Assessment {i} Description", f"Assessment {i} Student output",
        f"Assessment {i} Grading", f"Assessment {i} Indicative due week"
    ]



def scrape_unit(unit_code):
    unit_data = create_unit_template()
    unit_data["Unit Code"] = unit_code
    url = f"https://handbook.deakin.edu.au/courses-search/unit.php?unit={unit_code}"

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
    except Exception as e:
        unit_data["Unit Name"] = f"❌ Failed to load: {str(e)}"
        return unit_data

    content_div = soup.find("div", class_="content")
    if not content_div:
        unit_data["Unit Name"] = "❌ No content found"
        return unit_data

    h1_tag = content_div.find("h1")
    if h1_tag:
        full_title = h1_tag.get_text(strip=True)
        unit_data["Unit Name"] = full_title.split(" - ", 1)[-1] if " - " in full_title else full_title

    table = content_div.find("table", class_="table")
    if table:
        for row in table.find_all("tr"):
            th, td = row.find("th"), row.find("td")
            if not th or not td:
                continue
            label = th.get_text(strip=True).lower()
            value = td.get_text(separator=" ", strip=True)
            if "offering information" in label:
                unit_data["Offering information"] = value
            elif "enrolment mode" in label:
                unit_data["Enrolment modes"] = value
            elif "credit point" in label:
                unit_data["Credit Points"] = value
            elif "eftsl" in label:
                unit_data["EFTSL value"] = value
            elif "previously coded" in label:
                unit_data["Previously coded as"] = value
            elif "assumed knowledge" in label:
                unit_data["Assumed Knowledge"] = value
            elif "unit chair" in label:
                chairs = re.findall(r'Trimester (\d):\s*(.+?)(?=Trimester|$)', value)
                for tri, name in chairs:
                    unit_data[f"Unit Chair Trimester {tri}"] = name.strip()
            elif "prerequisite" in label:
                unit_data["Prerequisite"] = value
            elif "corequisite" in label:
                unit_data["Corequisite"] = value
            elif "incompatible" in label:
                unit_data["Incompatible with"] = value
            elif "on-campus" in label:
                unit_data["Learning activities - On-campus enrolment"] = value
            elif "online" in label:
                unit_data["Learning activities - Online enrolment"] = value
            elif "study commitment" in label:
                unit_data["Typical study commitment"] = value

    for h3 in content_div.find_all("h3"):
        heading = h3.get_text(strip=True).lower()
        content = []
        for sibling in h3.find_next_siblings():
            if sibling.name == "h3":
                break
            if sibling.name == "p":
                content.append(sibling.get_text(strip=True))
        text = " ".join(content)
        if "content" in heading:
            unit_data["Content"] = text
        elif "hurdle" in heading:
            unit_data["Hurdle requirement"] = text
        elif "learning resource" in heading:
            unit_data["Learning resource"] = text

    ulo_index = 1
    for h3 in content_div.find_all("h3"):
        if "learning outcomes" in h3.get_text(strip=True).lower():
            table = h3.find_next("table")
            if table:
                for row in table.find_all("tr")[1:]:
                    cells = row.find_all("td")
                    if len(cells) >= 3:
                        unit_data[f"ULO{ulo_index} Description"] = cells[1].get_text(strip=True)
                        unit_data[f"ULO{ulo_index} GLO Alignment"] = cells[2].get_text(separator=" ",strip=True)
                        ulo_index += 1
            break

    assess_index = 1
    for h3 in content_div.find_all("h3"):
        if "assessment" in h3.get_text(strip=True).lower():
            table = h3.find_next("table")
            if table:
                for row in table.find_all("tr")[1:]:
                    cells = row.find_all("td")
                    if len(cells) >= 4:
                        unit_data[f"Assessment {assess_index} Description"] = cells[0].get_text(separator=" ", strip=True)
                        unit_data[f"Assessment {assess_index} Student output"] = cells[1].get_text(strip=True)
                        unit_data[f"Assessment {assess_index} Grading"] = cells[2].get_text(strip=True)
                        unit_data[f"Assessment {assess_index} Indicative due week"] = cells[3].get_text(strip=True)
                        assess_index += 1
            break

    return unit_data

def scrape_units_in_background(unit_codes):
    global final_output
    results = []
    for i, code in enumerate(unit_codes, start=1):
        progress_messages.append(f"Scraping {code} ({i} of {len(unit_codes)})")
        unit_data = scrape_unit(code)
        results.append(unit_data)

    progress_messages.append("Scraping completed ✅")

    normalized = normalize_unit_data(results)
    output = BytesIO()
    pd.DataFrame(normalized).to_excel(output, index=False)
    output.seek(0)
    final_output = output

@app.route("/", methods=["GET", "POST"])
def index():
    global final_output
    final_output = None
    progress_messages.clear()

    if request.method == "POST":
        file = request.files["file"]
        if not file:
            return "No file uploaded", 400

        df = pd.read_excel(file)
        unit_codes = df.iloc[:, 0].dropna().astype(str).tolist()

        thread = threading.Thread(target=scrape_units_in_background, args=(unit_codes,))
        thread.start()

        while thread.is_alive():
            time.sleep(1)

        return send_file(final_output, download_name="scraped_units.xlsx", as_attachment=True)

    return render_template("index.html")

@app.route("/progress-stream")
def progress_stream():
    def event_stream():
        while True:
            if progress_messages:
                message = progress_messages.pop(0)
                yield f"data: {message}\n\n"
            time.sleep(0.5)
    return Response(event_stream(), mimetype="text/event-stream")

if __name__ == "__main__":
    app.run(debug=True)
