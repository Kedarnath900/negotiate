import io, pandas as pd
from pypdf import PdfReader

REQUIRED_COLUMNS=["supplier","category","quoted_price","target_price","delivery_days","payment_days","outcome"]
def make_sample_data():
    rows=[
    ["Apex Electronics","Electronics",10100,10000,18,45,"ACCEPT"],
    ["Northstar Components","Electronics",11200,10000,25,30,"COUNTER"],
    ["BrightPack Ltd","Packaging",920,900,15,45,"ACCEPT"],
    ["RapidMove Logistics","Logistics",1350,1200,28,15,"ESCALATE"],
    ["Core Materials","Raw materials",780,700,22,30,"COUNTER"],
    ["Delta Circuits","Electronics",12900,10000,19,60,"REJECT"],
    ["GreenWrap","Packaging",880,900,18,30,"ACCEPT"],
    ["Metro Freight","Logistics",1250,1200,20,30,"ACCEPT"],
    ["Nova Components","Electronics",10800,10000,26,45,"COUNTER"],
    ["Pioneer Polymers","Raw materials",950,800,35,15,"ESCALATE"],
    ["CloudDesk Services","IT services",5100,5000,10,60,"ACCEPT"],
    ["Eastline Packaging","Packaging",1100,900,20,30,"COUNTER"],
    ["Zenith Freight","Logistics",1600,1200,40,30,"REJECT"],
    ["Orion Materials","Raw materials",720,700,19,45,"ACCEPT"],
    ["Vertex Systems","IT services",5700,5000,18,30,"COUNTER"],
    ]
    return pd.DataFrame(rows,columns=REQUIRED_COLUMNS)

def read_uploaded_file(uploaded):
    name=uploaded.name.lower()
    raw=uploaded.getvalue()
    if name.endswith(".csv"):
        df=pd.read_csv(io.BytesIO(raw))
        return _normalize_df(df)
    if name.endswith(".xlsx"):
        df=pd.read_excel(io.BytesIO(raw))
        return _normalize_df(df)
    if name.endswith(".pdf"):
        reader=PdfReader(io.BytesIO(raw))
        text="\n".join(page.extract_text() or "" for page in reader.pages)
        return [{"supplier":uploaded.name.rsplit(".",1)[0],"category":"Unclassified",
                 "quoted_price":"","target_price":"","delivery_days":"","payment_days":"",
                 "outcome":"UNREVIEWED","notes":text[:12000]}]
    if name.endswith(".txt"):
        text=raw.decode("utf-8",errors="replace")
        return [{"supplier":uploaded.name.rsplit(".",1)[0],"category":"Unclassified",
                 "quoted_price":"","target_price":"","delivery_days":"","payment_days":"",
                 "outcome":"UNREVIEWED","notes":text[:12000]}]
    raise ValueError("Unsupported file format")

def _normalize_df(df):
    df.columns=[str(c).strip().lower().replace(" ","_") for c in df.columns]
    for c in REQUIRED_COLUMNS:
        if c not in df.columns: df[c]=""
    for c in ["quoted_price","target_price","delivery_days","payment_days"]:
        df[c]=pd.to_numeric(df[c], errors="coerce")
    for c in ["supplier","category","outcome"]:
        df[c]=df[c].fillna("").astype(str)
    df["outcome"]=df["outcome"].replace("", "UNREVIEWED")
    return df.to_dict("records")
