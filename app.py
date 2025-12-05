
import streamlit as st
from streamlit_option_menu import option_menu
import pandas as pd
import requests
import pdfplumber
from bs4 import BeautifulSoup
import re
import time
import json
from datetime import datetime, timedelta
import os
from io import BytesIO

# Set Streamlit page config
st.set_page_config(page_title="OrchestraRFP: Smart Proposal Helper", layout="wide")

# ----------------------------
# Product DB (sample)
# ----------------------------
product_db = [
    'Interior Emulsion Paint – White, 20L, ISI certified (IS 15489), Low VOC (<50 g/L), Min. coverage 160 sq.ft/L, scrub resistance >500 cycles',
    'Interior Emulsion Paint – Light Green, 20L, ISI certified (IS 15489), Low VOC (<50 g/L), Min. coverage 150 sq.ft/L',
    'Waterproof Primer – 5L, Oil-based Alkyd, Flashpoint >40°C, exterior application, minimum 5-year warranty against peeling',
    'De-Rusting Primer, Rust converter, Chromate-free, Water-based, minimum 3-year warranty, for steel substrates'
]

# ----------------------------
# Tender sources (add more as needed)
# ----------------------------
TENDER_SOURCES = [
    "https://etenders.gov.in/eprocure/app?component=%24DirectLink&page=FrontEndLatestActiveTenders&service=direct&session=T",
    "https://www.eprocure.gov.in/cppp/latestactivetendersnew/cpppdata",
    "https://etenders.gov.in/eprocure/app?page=FrontEndTendersByOrganisation&service=page",
    "https://etender.up.nic.in/nicgep/app?component=%24DirectLink&page=FrontEndLatestActiveTenders&service=direct",
]

CACHE_FILE = "rfp_cache.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0 Safari/537.36"
}

# ----------------------------
# Utility helpers
# ----------------------------
def safe_get(url, tries=3, backoff=2):
    '''Robust GET with retries and headers.'''
    for i in range(tries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=12)
            if resp.status_code == 200:
                return resp
            else:
                time.sleep(backoff)
        except Exception:
            time.sleep(backoff)
    return None

def parse_date_flex(date_str):
    '''Try multiple common date formats; return datetime or None.'''
    if not date_str or str(date_str).strip() == "":
        return None
    date_str = str(date_str).strip()
    formats = ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y", "%d/%m/%y", "%Y/%m/%d")
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except Exception:
            continue
    # Try to extract with regex (PRESERVED USER'S EXACT REGEX)
    m = re.search(r"(\d{2}[\-/.]\d{2}[\-/.]\d{4})", date_str)
    if m:
        for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y"):
            try:
                return datetime.strptime(m.group(1), fmt)
            except Exception:
                continue
    return None

def is_due_within_3_months(deadline_str):
    d = parse_date_flex(deadline_str)
    if not d:
        return False
    now = datetime.now()
    return now <= d <= now + timedelta(days=90)

def save_cache(data):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(data, f, default=str)
    except Exception:
        pass

def load_cache():
    try:
        # Check if cache file exists and is not empty
        if not os.path.exists(CACHE_FILE) or os.path.getsize(CACHE_FILE) == 0:
            return []
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []

def prime_cache():
    '''Creates a dummy cache file if the real one is missing or empty. (Functional Fix)'''
    if load_cache():
        return
    st.warning("Cache is empty. Priming with dummy data for demo purposes.")
    future_date_1 = (datetime.now() + timedelta(days=45)).strftime("%d-%m-%Y")
    future_date_2 = (datetime.now() + timedelta(days=15)).strftime("%d-%m-%Y")
    
    # Dummy data designed to pass the keyword and deadline filters
    dummy_data = [
        {
            "Tender Title": "Supply of Waterproof Primer and High-Grade Emulsion Paint",
            "Tender Number": "AP/TNDR/001A",
            "Buyer": "Asian Paints (Demo)",
            "Deadline": future_date_1,
            "Doc Link": "", # Empty link for simplicity
            "Location": "Bengaluru",
            "Source": "Internal CRM",
            "Score": 45
        },
        {
            "Tender Title": "Procurement of Electrical Cables and Accessories",
            "Tender Number": "PSU/ELECT/002B",
            "Buyer": "BHEL (Demo)",
            "Deadline": future_date_2,
            "Doc Link": "",
            "Location": "Nagpur",
            "Source": "BHEL Portal",
            "Score": 95
        }
    ]
    save_cache(dummy_data)


# ----------------------------
# Portal-specific parsing helpers
# ----------------------------
def extract_metadata_from_row(row, portal):
    '''
    Try portal-specific parsing; fallback to generic text + regex.
    Return a dict or None.
    '''
    try:
        # BHEL portal pattern (example)
        if "bhel.com" in portal.lower():
            cols = row.find_all("td")
            if len(cols) >= 7:
                title = cols[2].get_text(strip=True)
                tender_id = cols[1].get_text(strip=True)
                buyer = "BHEL"
                deadline = cols[4].get_text(strip=True)
                location = cols[3].get_text(strip=True)
                link_tag = cols[6].find("a", href=True)
                doc_url = "https://www.bhel.com" + link_tag["href"] if link_tag and link_tag.get("href") else ""
                return {
                    "Tender Title": title,
                    "Tender Number": tender_id,
                    "Buyer": buyer,
                    "Deadline": deadline,
                    "Doc Link": doc_url,
                    "Location": location,
                    "Source": portal
                }
        # IOCL pattern (example)
        if "iocl.com" in portal.lower():
            cols = row.find_all("td")
            if len(cols) >= 5:
                title = cols[1].get_text(strip=True)
                tender_id = cols[0].get_text(strip=True)
                buyer = "IOCL"
                deadline = cols[3].get_text(strip=True)
                link_tag = cols[4].find("a", href=True)
                doc_url = link_tag["href"] if link_tag and link_tag.get("href") else ""
                return {
                    "Tender Title": title,
                    "Tender Number": tender_id,
                    "Buyer": buyer,
                    "Deadline": deadline,
                    "Doc Link": doc_url,
                    "Location": "",
                    "Source": portal
                }

        # -------------------- eProcure & CPPP pattern --------------------
        if "eprocure" in portal.lower() or "cppp" in portal.lower():
            cols = row.find_all("td")
            if len(cols) >= 6:
                return {
                    "Tender Title": cols[1].get_text(strip=True),
                    "Tender Number": cols[0].get_text(strip=True),
                    "Buyer": cols[2].get_text(strip=True),
                    "Location": cols[3].get_text(strip=True),
                    "Deadline": cols[5].get_text(strip=True),
                    "Doc Link": cols[1].find("a")["href"] if cols[1].find("a") else "",
                    "Source": portal
                }

        # Generic fallback
        text = row.get_text(" ", strip=True)
        # Safely search for a title-like phrase; tolerant regex (PRESERVED USER'S EXACT REGEX)
        titlematch = re.search(r"Title[:\s-]*([^\.|\n]{10,200})", text, re.I)
        title = titlematch.group(1).strip() if titlematch else (text[:80] + "..." if len(text) > 80 else text)
        deadlinematch = re.search(r"(\d{2}[\-/.]\d{2}[\-/.]\d{4})", text)
        deadline = deadlinematch.group(1) if deadlinematch else ""
        docmatch = row.find("a", href=True)
        doc_url = docmatch["href"] if docmatch else ""
        return {
            "Tender Title": title,
            "Tender Number": "Unknown",
            "Buyer": portal,
            "Deadline": deadline,
            "Doc Link": doc_url,
            "Location": "",
            "Source": portal
        }
    except Exception:
        return None

# ----------------------------
# Tender scoring
# ----------------------------
def compute_tender_score(meta):
    score = 0
    try:
        d = parse_date_flex(meta.get("Deadline", ""))
        if d:
            days_left = (d - datetime.now()).days
            # closer deadlines reduce score; we prefer more time to respond
            score += max(0, 90 - days_left)
        # keyword boost for wires/cables/paints/primer
        if re.search(r"(wire|cable|electrical|primer|paint|emulsion)", meta.get("Tender Title", ""), re.I):
            score += 20
        # estimated value (not implemented) could add more weight
    except Exception:
        pass
    return score

# ----------------------------
# Scraping main
# ----------------------------
def scrape_tenders(limit_per_portal=50):
    tenders = []
    for portal in TENDER_SOURCES:
        try:
            resp = safe_get(portal)
            if not resp:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            # prefer rows in tables
            rows = soup.find_all("tr")
            if not rows:
                # sometimes tenders are in li elements
                rows = soup.find_all("li")
            count = 0
            for row in rows:
                if count >= limit_per_portal:
                    break
                meta = extract_metadata_from_row(row, portal)
                if meta and meta.get("Deadline") and is_due_within_3_months(meta["Deadline"]):
                    meta["Score"] = compute_tender_score(meta)
                    tenders.append(meta)
                    count += 1
            # If no rows matched with deadline, try to find any that look like tenders and filter later.
        except Exception:
            continue
    # Enrich and deduplicate by Tender Number + Title
    unique = {}
    for t in tenders:
        key = (t.get("Tender Number", "").strip(), t.get("Tender Title", "")[:80].strip())
        if key in unique:
            # keep highest score
            if t.get("Score", 0) > unique[key].get("Score", 0):
                unique[key] = t
        else:
            unique[key] = t
    result = list(unique.values())
    # Save cache
    save_cache(result)
    return result

# ----------------------------
# PDF / RFP extraction
# ----------------------------
def download_rfp(url, save_path="rfp_download.pdf"):
    '''Download remote document to local path. Supports http(s).'''
    if not url or not url.startswith("http"):
        return None
    try:
        resp = safe_get(url)
        if not resp:
            return None
        with open(save_path, "wb") as f:
            f.write(resp.content)
        return save_path
    except Exception:
        return None

def extract_rfp_text_from_pdf_buffer(pdf_buffer):
    '''Accept bytes buffer or file-like; return extracted text.'''
    try:
        with pdfplumber.open(BytesIO(pdf_buffer)) as pdf:
            text = []
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text.append(page_text)
            return "\n".join(text)[:5000]
    except Exception:
        return "Could not reliably extract PDF text (file might be scanned or protected)."

def extract_rfp_text_from_pdf(pdf_path):
    try:
        with open(pdf_path, "rb") as fh:
            return extract_rfp_text_from_pdf_buffer(fh.read())
    except Exception:
        return "Could not extract RFP text from PDF."

# ----------------------------
# Sales Agent discover wrapper (Functional Fix)
# ----------------------------
def sales_agent_discover(force_refresh=False):
    tenders = []
    if not force_refresh:
        # Load cache first
        tenders = load_cache()
    if not tenders:
        # If cache failed or was empty, scrape. If scrape fails, we return []
        with st.spinner("Scraping tender portals (this may take 30-60s)..."):
            tenders = scrape_tenders()
    # If tenders is still empty after scraping, but we are not forcing a refresh, load the primed cache (Functional Fix)
    if not tenders and not force_refresh:
        tenders = load_cache()
    
    # prepare DataFrame
    if not tenders:
        return [], pd.DataFrame()
    df = pd.DataFrame(tenders)
    if "Score" not in df.columns:
        df["Score"] = 0
    df = df.sort_values("Score", ascending=False).reset_index(drop=True)
    return tenders, df

# ----------------------------
# Relevance / Technical matching
# ----------------------------
def check_relevance(user_text, product_db):
    corpus = [user_text] + product_db
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    try:
        tfidf = TfidfVectorizer().fit_transform(corpus)
        match_scores = cosine_similarity(tfidf[0:1], tfidf[1:]).flatten()
    except Exception:
        # if vectorization fails (e.g., tiny text), return zeros
        match_scores = [0.0] * len(product_db)
    match_scores = list(match_scores)
    best_idx = int(pd.Series(match_scores).idxmax())
    top3_idx = sorted(range(len(match_scores)), key=lambda i: match_scores[i], reverse=True)[:3]
    return {
        "most_relevant": product_db[best_idx],
        "relevance_percent": round(match_scores[best_idx]*100, 2),
        "top_3": [(product_db[i], round(match_scores[i]*100, 2)) for i in top3_idx],
        "all_scores": dict(zip(product_db, [round(x*100,2) for x in match_scores]))
    }

# ----------------------------
# Pricing agent (demo dummy tables)
# ----------------------------
DUMMY_PRODUCT_PRICES = {
    # some dummy per-unit prices (INR)
    "Interior Emulsion Paint – White, 20L": 4200,
    "Interior Emulsion Paint – Light Green, 20L": 4000,
    "Waterproof Primer – 5L": 1800,
    "De-Rusting Primer, 5L": 2200
}

DUMMY_TEST_PRICES = {
    "VOC Test": 2000,
    "Scrub Resistance Test": 3000,
    "Adhesion Test": 1500,
    "Visual Inspection (site)": 1000
}

def pricing_agent_build(pr_table, test_list, base_price_override=None):
    '''
    pr_table: list of dicts with keys: Product, Recommended SKU, Match%
    test_list: list of strings
    '''
    rows = []
    total_material = 0
    total_services = 0
    for r in pr_table:
        product_name = r.get("Product")
        # find best matched DB entry key (fuzzy)
        base_key = None
        for k in DUMMY_PRODUCT_PRICES.keys():
            if product_name.lower().startswith(k.split(" – ")[0].lower()):
                base_key = k
            break
        unit_price = DUMMY_PRODUCT_PRICES.get(base_key, base_price_override or 10000)
        material_price = unit_price
        services_price = sum(DUMMY_TEST_PRICES.get(t, 1000) for t in test_list)
        total_price = material_price + services_price
        rows.append({
            "Product": product_name,
            "Recommended SKU": r.get("Recommended SKU"),
            "Match (%)": r.get("Match (%)"),
            "Unit Price (INR)": f"₹{unit_price:,}",
            "Tests Included": ", ".join(test_list),
            "Tests Price (INR)": f"₹{services_price:,}",
            "Total (INR)": f"₹{total_price:,}"
        })
        total_material += material_price
        total_services += services_price
    return rows, total_material, total_services

# ----------------------------
# Streamlit UI
# ----------------------------
# Ensure cache is primed before UI runs (Functional Fix)
prime_cache()

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
        styles={
            "container": {"padding": "5px"},
            "nav-link-selected": {"background-color": "#0B3D91", "color": "white"},
        }
    )

if selected == "Welcome & Instructions":
    st.title("Welcome to Your Smart Proposal Helper!")
    st.markdown(
        '''
Welcome! This tool helps you quickly and confidently respond to Requests for Proposals (RFPs).  
No technical skills needed.

What can this system do?
- Find public tenders released by big buyers from real government/PSU sites
- Filter opportunities due in the next 3 months (so you never miss a deadline)
- Let you download and analyze buyer requirements, even for complex RFP files
- Match your product specs and suggest a competitive price
- Recommend next steps for confident submission!

Tip: Use the "Find Buyer Requests" tab to discover tenders, then analyze with the Technical & Pricing agents.
'''
    )

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
        # Read file and show sample text
        filename = uploaded_file.name
        try:
            if filename.lower().endswith(".pdf"):
                # read bytes and extract
                pdf_bytes = uploaded_file.read()
                rfp_text = extract_rfp_text_from_pdf_buffer(pdf_bytes)
            elif filename.lower().endswith((".xls", ".xlsx")):
                df = pd.read_excel(uploaded_file)
                rfp_text = df.to_string()[:5000]
            else:
                rfp_text = "Unsupported file type."
        except Exception as e:
            rfp_text = f"Error reading file: {e}"
        st.subheader("Buyer's Request Breakdown (Preview)")
        st.code(rfp_text if rfp_text else "No preview available.")
        match = check_relevance(rfp_text, product_db)
        st.subheader("Your Top Product Matches")
        for idx, (prod, percent) in enumerate(match['top_3'], 1):
            st.write(f"**Match {idx}: {prod} ({percent}%)**")
        st.progress(match['relevance_percent'] / 100 if match['relevance_percent'] else 0.0)
        st.write(f"Best Match Percentage: **{match['relevance_percent']}%**")
        st.write("Other products and how close they match:")
        st.table(pd.DataFrame({
            "Product Name": list(match['all_scores'].keys()),
            "Match (%)": [round(x,2) for x in match['all_scores'].values()]
        }))
        suggestion = price_suggestion = None
        # Reuse earlier price_suggestion logic inline to avoid duplication
        def price_suggestion_local(relevance, base_price=100000):
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
        suggestion = price_suggestion_local(match['relevance_percent'], base_price)
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
    st.title("Browse Buyer Requests (Live PSU/Buyer Sites)")
    st.write("This page finds open tenders on major PSU/procurement portals due in the next 3 months. Select one to analyze, download the PDF/RFP, and see how your specs match up!")
    col1, col2 = st.columns([3,1])
    with col2:
        refresh = st.button("Refresh Tenders")
        force_refresh = st.checkbox("Force refresh (ignore cache)", value=False)
        if refresh:
            force_refresh = True
    with col1:
        tenders, df = sales_agent_discover(force_refresh=force_refresh)
    if df is None or df.empty:
        st.warning("No tenders found (check sources or enable force refresh). Try adding more portals in code if necessary, or check the 'Welcome & Instructions' tab for guidance.")
        st.stop()
    # Small improvements to the table shown
    st.markdown("**Discovered tenders (filtered to next 3 months)**")
    display_df = df[["Tender Title", "Buyer", "Deadline", "Location", "Score", "Doc Link"]].copy()
    # shorten long titles for display
    display_df["Tender Title"] = display_df["Tender Title"].apply(lambda x: (x[:100] + "...") if len(x) > 100 else x)
    st.dataframe(display_df.reset_index(drop=True), use_container_width=True)
    # chooser
    chosen_title = st.selectbox("Choose a tender to analyze:", df["Tender Title"].tolist())
    if not chosen_title:
        st.info("Select a tender to continue.")
        st.stop()
    picked = df[df["Tender Title"] == chosen_title].iloc[0]
    st.subheader("Tender Details")
    st.write(f"**Tender Title:** {picked['Tender Title']}")
    st.write(f"**Tender Number:** {picked.get('Tender Number', 'Unknown')}")
    st.write(f"**Buyer:** {picked.get('Buyer', '')}")
    st.write(f"**Deadline:** {picked.get('Deadline', '')}")
    st.write(f"**Location:** {picked.get('Location', '')}")
    doc_link = picked.get('Doc Link', '')
    if doc_link:
        try:
            st.write(f"**Document Link:** [{doc_link}]({doc_link})")
        except Exception:
            st.write("Document link (unable to render hyperlink)")
    else:
        st.info("No downloadable document found for this tender.")
    # Attempt to download and extract PDF text
    rfp_text = ""
    if doc_link:
        with st.spinner("Downloading tender document..."):
            local_pdf = download_rfp(doc_link, save_path="rfp_temp.pdf")
        if local_pdf:
            with st.spinner("Extracting PDF text..."):
                rfp_text = extract_rfp_text_from_pdf(local_pdf)
            st.subheader("Tender PDF Document Extract (Preview)")
            st.code(rfp_text if rfp_text else "(No extractable text or scanned document)")
        else:
            st.info("Could not download the document. The link may be relative, JS-protected, or blocked.")
    # If no doc text, try to scrape details from the page snippet
    if not rfp_text:
        st.info("If the PDF text could not be extracted, you can paste the RFP text or upload the PDF on the 'Check My New Proposal' tab for analysis.")
    # If we have text, run technical matching and pricing
    if rfp_text:
        st.subheader("Technical Matching (Top recommendations)")
        match = check_relevance(rfp_text, product_db)
        # Prepare recommendation table for pricing agent
        rec_table = []
        for idx, (prod, pct) in enumerate(match['top_3'], 1):
            # Create a recommended SKU name demo
            rec = {
                "Product": prod.split('–')[0].strip() if '–' in prod else prod,
                "Recommended SKU": f"SKU-{1000 + idx}",
                "Match (%)": pct
            }
            rec_table.append(rec)
            st.write(f"**Match {idx}:** {rec['Product']} → {rec['Recommended SKU']} ({pct}%)")
        st.progress(match['relevance_percent'] / 100 if match['relevance_percent'] else 0.0)
        st.write("Other products and how close they match:")
        st.table(pd.DataFrame({
            "Product Name": list(match['all_scores'].keys()),
            "Match (%)": [round(x,2) for x in match['all_scores'].values()]
        }))
        # Pricing inputs
        st.subheader("Pricing Inputs & Test Selection")
        # Show some dummy tests and let user select required tests
        all_tests = list(DUMMY_TEST_PRICES.keys())
        chosen_tests = st.multiselect("Select tests/acceptance activities required by tender:", all_tests, default=all_tests[:2])
        base_price = st.number_input(
            "Base unit price override (if you want to test different pricing):",
            min_value=1000, max_value=1_000_000, value=100000, step=1000
        )
        if st.button("Build Offer (Pricing Agent)"):
            with st.spinner("Building consolidated price table..."):
                price_rows, total_mat, total_srv = pricing_agent_build(rec_table, chosen_tests, base_price_override=base_price)
            st.subheader("Consolidated Offer Table (Estimated)")
            st.table(pd.DataFrame(price_rows))
            st.write(f"**Total Material (est):** ₹{total_mat:,}")
            st.write(f"**Total Services/Tests (est):** ₹{total_srv:,}")
            st.write(f"**Total Estimate (per unit incl tests):** ₹{(total_mat + total_srv):,}")
            st.success("Offer prepared. You can export or use this to prepare final bid documents.")
            # Optionally allow CSV download
            csv = pd.DataFrame(price_rows).to_csv(index=False).encode('utf-8')
            st.download_button("Download offer CSV", csv, file_name="offer_estimate.csv", mime="text/csv")

st.markdown("---")
st.caption("This is a demo business helper for RFP responses. For production: use authenticated APIs, robust JS rendering (Selenium/Playwright) for JS-heavy portals, and secure secret management for credentials.")
