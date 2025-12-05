
import streamlit as st
from streamlit_option_menu import option_menu
import pandas as pd
import pdfplumber
import requests
from bs4 import BeautifulSoup
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

st.set_page_config(page_title="OrchestraRFP: Smart Proposal Helper", layout="wide")

# Product list: These are examples of what your company offers.
product_db = [
    'Interior Emulsion Paint – White, 20L, ISI certified (IS 15489), Low VOC (<50 g/L), Min. coverage 160 sq.ft/L, scrub resistance >500 cycles',
    'Interior Emulsion Paint – Light Green, 20L, ISI certified (IS 15489), Low VOC (<50 g/L), Min. coverage 150 sq.ft/L',
    'Waterproof Primer – 5L, Oil-based Alkyd, Flashpoint >40°C, exterior application, minimum 5-year warranty against peeling',
    'De-Rusting Primer, Rust converter, Chromate-free, Water-based, minimum 3-year warranty, for steel substrates'
]

def read_proposal_file(file):
    # Reads PDF/Excel and shows summary
    text = ""
    filename = file.name if hasattr(file, "name") else str(file)
    if filename.endswith(".pdf"):
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    elif filename.endswith(".xlsx") or filename.endswith(".xls"):
        df = pd.read_excel(file)
        text = df.to_string()
    else:
        text = "Unsupported file type."
    return {
        "name": "Uploaded Proposal",
        "details": text[:800],
        "source": filename
    }

def check_relevance(user_text, product_db):
    # Compares buyer request with company products
    corpus = [user_text] + product_db
    tfidf = TfidfVectorizer().fit_transform(corpus)
    match_scores = cosine_similarity(tfidf[0:1], tfidf[1:]).flatten()
    best_idx = match_scores.argmax()
    return {
        "most_relevant": product_db[best_idx],
        "relevance_percent": round(match_scores[best_idx]*100, 2),
        "all_scores": dict(zip(product_db, match_scores * 100))
    }

def price_suggestion(relevance, base_price=100000):
    relevance_factor = relevance / 100
    price = int(base_price * relevance_factor)
    score = round(10 * relevance_factor, 2)
    if score > 7:
        note = "Great match! Submitting this offer is recommended."
    else:
        note = "This offer is not a strong match. Please review with your team before submitting."
    return {
        "price": f"₹{price:,}",
        "score": score,
        "advice": note
    }

def get_demo_requests():
    # Website scrape (demo only) or fallback
    url = "https://www.python.org/jobs/"
    try:
        resp = requests.get(url)
        soup = BeautifulSoup(resp.text, "html.parser")
        jobs = soup.select("ul.list-recent-jobs li")
        output = []
        for job in jobs[:5]:
            title = job.find("h2").get_text(strip=True)
            company = job.find("span", class_="listing-company-name")
            company = company.get_text(strip=True) if company else "Unknown"
            deadline = job.find("span", class_="listing-posted")
            deadline = deadline.get_text(strip=True) if deadline else "Not listed"
            link = "https://www.python.org" + job.find("a", href=True)["href"]
            output.append({
                "Title": title,
                "Company": company,
                "Deadline": deadline,
                "Details": f"Company: {company}\nRole: {title}\nDeadline: {deadline}",
                "Source": link
            })
    except Exception as e:
        output = []
    if not output:
        output = [
            {
                "Title": "Supply of Interior Paints for Bengaluru Plant",
                "Company": "Asian Paints",
                "Deadline": "2026-02-15",
                "Details": "Interior Emulsion Paint, ISI certified, 20L cans.",
                "Source": "https://example.com/rfp1"
            },
            {
                "Title": "Order of De-Rusting Primer (Steel Pipes)",
                "Company": "APSP",
                "Deadline": "2026-04-10",
                "Details": "De-Rusting Primer, water-based, warranty 3 years.",
                "Source": "https://example.com/rfp2"
            }
        ]
    return output

with st.sidebar:
    selected = option_menu(
        "OrchestraRFP Menu",
        [
            "Welcome & Instructions",
            "My Recent Proposals",
            "Check My New Proposal",
            "Find Buyer Requests"
        ],
        menu_icon="cast",
        icons=["house", "list-task", "cloud-upload", "globe2"],
        styles={"nav-link-selected": {"background-color": "#0B3D91", "color": "white"}}
    )

if selected == "Welcome & Instructions":
    st.title("Welcome to Your Smart Proposal Helper!")
    st.markdown("""
Welcome! This tool helps you quickly and confidently respond to Requests for Proposals (RFPs).  
**You DON'T need any technical skills.**
    
**What can this system do?**
- Read your buyer's proposal file (PDF/Excel)
- Compare it with your product list
- Suggest the chance of success and a matching price
- Advise you whether to submit or review further

**How to use?**
- Use the side menu to upload a proposal or find buyer requests.
- Follow the on-screen steps. All feedback is in clear language!
                """)

elif selected == "My Recent Proposals":
    st.title("My Recent Proposals")
    st.info("Demo: shows what a full-featured dashboard could look like.")
    st.table(pd.DataFrame([
        {"Proposal": "Bulk Interior Paint – AP", "Status": "Submitted", "Chance (%)": 82.5, "Price": "₹82,500", "Due": "2025-12-20"},
        {"Proposal": "Water Repellent – Western India", "Status": "Needs Review", "Chance (%)": 55.9, "Price": "₹55,900", "Due": "2025-12-24"},
    ]))

elif selected == "Check My New Proposal":
    st.title("Check Your New Proposal")
    st.write("Easily check how well your products fit a buyer's requirements. Upload your file below.")
    uploaded_file = st.file_uploader("Upload your RFP or proposal file (PDF, XLS/XLSX):", type=['pdf', 'xlsx', 'xls'])
    base_price = st.number_input(
        "Enter your usual selling price (₹ per item):",
        min_value=1000, max_value=1_000_000, value=100000, step=1000
    )
    if uploaded_file:
        result = read_proposal_file(uploaded_file)
        st.subheader("Buyer's Request Breakdown")
        st.write(f"File: **{result['source']}**")
        st.code(result["details"], language="text")
        match = check_relevance(result["details"], product_db)
        st.subheader("Your Product Match")
        st.write(f"Product most like the request: **{match['most_relevant']}**")
        st.progress(match['relevance_percent'] / 100)
        st.write(f"Match Percentage: **{match['relevance_percent']}%**")
        st.write("Other products and how close they match:")
        st.table(pd.DataFrame({
            "Product Name": list(match['all_scores'].keys()),
            "Match (%)": [round(x,2) for x in match['all_scores'].values()]
        }))
        suggestion = price_suggestion(match['relevance_percent'], base_price)
        st.subheader("Suggested Price & Advice")
        st.write(f"Suggested Price: **{suggestion['price']}**")
        st.write(f"Success Score (out of 10): **{suggestion['score']}**")
        st.info(suggestion['advice'])
        if suggestion['score'] > 7:
            st.success("Recommended: Your offer is a strong match! Consider submitting.")
        else:
            st.warning("Recommended: Review with team before responding. Offer may need improvement.")
    else:
        st.info("When you upload your file, your results will appear here.")

elif selected == "Find Buyer Requests":
    st.title("Browse Buyer Requests (Demo)")
    st.write("See buyer needs or open requests, then check your match with one click below.")
    scraped = get_demo_requests()
    df_scraped = pd.DataFrame(scraped)
    st.table(df_scraped[["Title", "Company", "Deadline"]])
    chosen = st.selectbox("Choose a request to check your product match:", df_scraped["Title"].tolist())
    if st.button("Check Fit for This Request"):
        picked = df_scraped[df_scraped["Title"] == chosen].iloc[0]
        st.subheader("Buyer Request")
        st.write(f"Company: **{picked['Company']}**")
        st.write(f"Role/Item: **{picked['Title']}**")
        st.write(f"Deadline: **{picked['Deadline']}**")
        st.code(picked['Details'], language="text")
        match = check_relevance(picked["Details"], product_db)
        st.subheader("Your Product Match")
        st.write(f"Product most like the request: **{match['most_relevant']}**")
        st.progress(match['relevance_percent']/100)
        st.write(f"Match Percentage: **{match['relevance_percent']}%**")
        st.write("Other products and their closeness:")
        st.table(pd.DataFrame({
            "Product Name": list(match['all_scores'].keys()),
            "Match (%)": [round(x,2) for x in match['all_scores'].values()]
        }))
        base_price = st.number_input(
            "Enter your usual selling price (₹ per item):",
            min_value=1000, max_value=1_000_000, value=100000, step=1000,
            key="buyer_req_price"
        )
        suggestion = price_suggestion(match['relevance_percent'], base_price)
        st.subheader("Suggested Price & Advice")
        st.write(f"Suggested Price: **{suggestion['price']}**")
        st.write(f"Success Score (out of 10): **{suggestion['score']}**")
        st.info(suggestion['advice'])
        if suggestion['score'] > 7:
            st.success("Recommended: Submit your offer for this request!")
        else:
            st.warning("Consider reviewing with your team before responding. Offer may need updating.")

st.markdown("---")
st.caption("This is a simple business helper for RFP response—no technical knowledge required. Upload, get a match, and succeed!")

